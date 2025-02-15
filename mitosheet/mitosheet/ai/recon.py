import ast
import traceback
from copy import copy
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal
from mitosheet.ai.ai_utils import fix_up_missing_imports, get_code_string_from_last_expression, replace_last_instance_in_string

from io import StringIO
from contextlib import redirect_stdout

from mitosheet.errors import make_exec_error
from mitosheet.state import DATAFRAME_SOURCE_AI, State
from mitosheet.step_performers.column_steps.delete_column import \
    delete_column_ids
from mitosheet.step_performers.dataframe_steps.dataframe_delete import \
    delete_dataframe_from_state
from mitosheet.types import (AITransformFrontendResult, ColumnHeader,
                             ColumnReconData, DataframeReconData, ModifiedDataframeReconData)

def is_df_changed(old: pd.DataFrame, new: pd.DataFrame) -> bool:
    try:
        assert_frame_equal(old, new, check_names=False)
        return False
    except AssertionError:
        return True

def exec_for_recon(code: str, original_df_map: Dict[str, pd.DataFrame]) -> DataframeReconData:
    """
    Given some Python code, and a list of previously defined dataframes, this function:
    1. Gets all the newly defined dataframes
    2. Gets all the dataframes that have been modified
    3. Gets the value of the last line of code, if that is a Python expression (e.g. not defining a variable)

    It does all of this while only execing the code a single time, which helps performance.

    To find newly defined dataframes, we just save the local variables before the exec runs, 
    and then find any new dataframes in locals after the exec runs.

    To find the modified dataframes, we capture any dataframe names that are referenced in the code
    as potentially modified and add them as a local. This then allows us to get out the new values 
    of that dataframe, and compare them to the old one to see if they really changed.

    Finially, getting the value of the last line requires parsing the Python AST, checking the
    last expressio, then rebuilding it into a string (aka so we can handle multiple lines) - 
    and then saving it in fake variable that we can then access again through the locals.
    """
    if len(code) == 0:
        return {
            'created_dataframes': {},
            'deleted_dataframes': [],
            'modified_dataframes': {},
            'last_line_expression_value': None,
            'prints': ''
        }

    df_map = {df_name: df.copy(deep=True) for df_name, df in original_df_map.items()}
    locals_before = copy(locals())
    try:
        ast_before = ast.parse(code)
    except SyntaxError as e:
        raise make_exec_error(e)

    try:
        last_expression = ast_before.body[-1]
    except:
        raise make_exec_error(Exception('No code was generated'))
    
    if not isinstance(last_expression, ast.Expr):
        has_last_line_expression_value = False
    else:
        has_last_line_expression_value = True
        # (The type ignore is b/c we know this has a value b/c of above check, mypy is not smart enough)
        last_expression_string: str = get_code_string_from_last_expression(code) #type: ignore
        code = replace_last_instance_in_string(code, last_expression_string, f'FAKE_VAR_NAME = {last_expression_string}')
    
    potentially_modified_df_names = [
        df_name for df_name in original_df_map if 
        df_name in code
    ]

    for df_name in potentially_modified_df_names:
        locals()[df_name] = df_map[df_name]

    # Capture the output as well
    output_string_io = StringIO()

    try:
        with redirect_stdout(output_string_io):
            exec(code, {}, locals())
    except Exception as e:
        raise make_exec_error(e)
        
    # We make a copy of locals, as the local variables redefine themselves in 
    # list comprehensions... sometimes. I don't get what is happening here, but it works
    new_locals = locals()

    created_dataframes: Dict[str, pd.DataFrame] = {
        name: value for name, value in new_locals.items()
        if name not in locals_before and name != 'locals_before' and name != 'FAKE_VAR_NAME'
        and isinstance(value, pd.DataFrame) and name not in original_df_map
    }

    deleted_dataframes = [
        name for name in df_map if name not in new_locals and name in potentially_modified_df_names
    ]

    modified_dataframes = {
        name: value for name, value in new_locals.items()
        if isinstance(value, pd.DataFrame) and name in potentially_modified_df_names
        and is_df_changed(original_df_map[name], value)
    }

    if has_last_line_expression_value:
        last_line_expression_value = locals()['FAKE_VAR_NAME']
    else:
        last_line_expression_value = None

    return {
        'created_dataframes': created_dataframes,
        'deleted_dataframes': deleted_dataframes,
        'modified_dataframes': modified_dataframes,
        'last_line_expression_value': last_line_expression_value,
        'prints': output_string_io.getvalue()
    }

def get_modified_dataframe_recon_data(old_df: pd.DataFrame, new_df: pd.DataFrame) -> ModifiedDataframeReconData:
    """
    Given a dataframe and a modified dataframe, this function tries to figure out what has happened
    to column headers dataframe. Specifically, because our state maps column headers to do others based on column
    id, we need to track which columns are added, which are removed, and which are renamed.
    """

    old_columns = old_df.columns.to_list()
    new_columns = new_df.columns.to_list()

    old_df_head = old_df.head(5)
    new_df_head = new_df.head(5)

    rows_added_or_removed = len(old_df) != len(new_df)

    # First, preserving the order, we remove any columns that are in both the old
    # and the new dataframe
    old_columns_without_shared = list(filter(lambda ch: ch not in new_columns, old_columns))
    new_columns_without_shared = list(filter(lambda ch: ch not in old_columns, new_columns))
    
    # Then, we look through to find any columns that have been simply renamed - simply
    # by comparing to see of column are identical between the two values. We do this 
    # just by checking the first 5 values of the dataframe, before doing a direct comparison
    renamed_columns: Dict[ColumnHeader, ColumnHeader] = {}
    for old_ch in old_columns_without_shared:
        old_column = old_df_head[old_ch]
        for new_ch in new_columns_without_shared:
            new_column = new_df_head[new_ch]
            if old_column.equals(new_column) and new_ch not in renamed_columns.values():
                renamed_columns[old_ch] = new_ch

    added_columns = [ch for ch in new_columns_without_shared if ch not in renamed_columns.values()]
    removed_columns = [ch for ch in old_columns_without_shared if ch not in renamed_columns]

    shared_columns = list(filter(lambda ch: ch in new_columns, old_columns))

    if not rows_added_or_removed:
        modified_columns = [ch for ch in shared_columns if not old_df[ch].equals(new_df[ch])]
    else:
        # If rows were added or removed, then we don't want to detect every column as having changed
        # and instead we'd just like to report the row changes. As such, we only compare the rows not added or removed
        # NOTE: this is not perfect, as you may have modified columns and removed rows in one go -- but this 
        # is ok for most of what we see
        try:
            if len(old_df) < len(new_df):
                df1 = old_df
                df2 = new_df.iloc[old_df.index]
            else:
                df1 = old_df.iloc[new_df.index]
                df2 = new_df

            modified_columns = [ch for ch in shared_columns if not df1[ch].equals(df2[ch])]
        except IndexError:
            modified_columns = [ch for ch in shared_columns if not old_df[ch].equals(new_df[ch])]

    return {
        'column_recon': {
            'created_columns': added_columns,
            'deleted_columns': removed_columns,
            'modified_columns': modified_columns,
            'renamed_columns': renamed_columns,
        },
        'num_added_or_removed_rows': len(new_df) - len(old_df)
    }
    


def exec_and_get_new_state_and_result(state: State, code: str) -> Tuple[State, Optional[Any], AITransformFrontendResult]:

    # Fix up the code, so we can ensure that we execute it properly
    code = fix_up_missing_imports(code)

    # Make deep copies of all dataframes here, so we can manipulate them without fear
    # TODO: in the future, we could just do the modified ones
    new_state = state.copy(deep_sheet_indexes=list(range(len(state.dfs))))

    df_map = {df_name: df for df_name, df in zip(new_state.df_names, new_state.dfs)}
    recon_data = exec_for_recon(code, df_map)

    # For all of the added dataframes, we just add them to the state
    for df_name, df in recon_data['created_dataframes'].items():
        new_state.add_df_to_state(df, DATAFRAME_SOURCE_AI, df_name=df_name)

    # For deleted dataframes, we remove them from the state
    for df_name in recon_data['deleted_dataframes']:
        delete_dataframe_from_state(new_state, new_state.df_names.index(df_name))
    
    # For modified dataframes, we update all the column variables
    modified_dataframes_recons: Dict[str, ModifiedDataframeReconData] = {}
    for df_name, new_df in recon_data['modified_dataframes'].items():
        sheet_index = new_state.df_names.index(df_name)
        old_df = df_map[df_name]
        modified_dataframe_recon = get_modified_dataframe_recon_data(old_df, new_df)
        modified_dataframes_recons[df_name] = modified_dataframe_recon

        # Add new columns to the state
        new_state.add_columns_to_state(sheet_index, modified_dataframe_recon['column_recon']['created_columns'])

        # Delete removed columns from the state
        deleted_column_ids = new_state.column_ids.get_column_ids_by_headers(sheet_index, modified_dataframe_recon['column_recon']['deleted_columns'])
        delete_column_ids(new_state, sheet_index, deleted_column_ids)

        # Rename renamed columns in the state
        for old_ch, new_ch in modified_dataframe_recon['column_recon']['renamed_columns'].items():
            column_id = new_state.column_ids.get_column_id_by_header(sheet_index, old_ch)
            new_state.column_ids.set_column_header(sheet_index, column_id, new_ch)

        # Then, actually set the dataframe
        new_state.dfs[sheet_index] = new_df

    # For the last value, if is a dataframe, then add it to the state as well -- unless this dataframe
    # is a _newly_ created dataframe that is already given a name
    last_line_expression_value = recon_data['last_line_expression_value']
    last_line_expression_code = get_code_string_from_last_expression(code)
    last_line_expression_is_previously_created_dataframe = last_line_expression_code in recon_data['created_dataframes']
    if (isinstance(last_line_expression_value, pd.DataFrame) or isinstance(last_line_expression_value, pd.Series)) and not last_line_expression_is_previously_created_dataframe:

        # If we get a series, we turn it into a dataframe for the user
        if isinstance(last_line_expression_value, pd.Series):
            last_line_expression_value = pd.DataFrame(last_line_expression_value, index=last_line_expression_value.index)

        new_state.add_df_to_state(last_line_expression_value, DATAFRAME_SOURCE_AI)
        # We also need to add this to the list of created dataframes, as we didn't know it's name till now
        recon_data['created_dataframes'][new_state.df_names[-1]] = last_line_expression_value

    # If the last line value is a primitive, we return it as a result for the frontend
    result_last_line_value = None
    if isinstance(last_line_expression_value, str) or isinstance(last_line_expression_value, bool) \
        or isinstance(last_line_expression_value, int) or isinstance(last_line_expression_value, float) \
            or isinstance(last_line_expression_value, np.number):
        result_last_line_value = last_line_expression_value

    frontend_result: AITransformFrontendResult = {
        'last_line_value': result_last_line_value,
        'created_dataframe_names': list(recon_data['created_dataframes'].keys()),
        'deleted_dataframe_names': recon_data['deleted_dataframes'],
        'modified_dataframes_recons': modified_dataframes_recons,
        'prints': recon_data['prints']
    }

    return (new_state, recon_data['last_line_expression_value'], frontend_result)

        
        

