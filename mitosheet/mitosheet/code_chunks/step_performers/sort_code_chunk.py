#!/usr/bin/env python
# coding: utf-8

# Copyright (c) Saga Inc.
# Distributed under the terms of the GPL License.

from typing import List, Optional

from mitosheet.code_chunks.code_chunk import CodeChunk
from mitosheet.code_chunks.code_chunk_utils import get_right_combine_with_column_delete_code_chunk
from mitosheet.code_chunks.step_performers.column_steps.delete_column_code_chunk import DeleteColumnsCodeChunk
from mitosheet.transpiler.transpile_utils import column_header_to_transpiled_code

class SortCodeChunk(CodeChunk):

    def get_display_name(self) -> str:
        return 'Sorted a column'
    
    def get_description_comment(self) -> str:
        sheet_index = self.get_param('sheet_index')
        column_id = self.get_param('column_id')
        column_header = self.post_state.column_ids.get_column_header_by_id(sheet_index, column_id)
        return f'Sorted {column_header}'

    def get_code(self) -> List[str]:
        from mitosheet.step_performers.sort import ASCENDING

        sheet_index = self.get_param('sheet_index')
        column_id = self.get_param('column_id')
        sort_direction = self.get_param('sort_direction')

        df_name = self.post_state.df_names[sheet_index]
        column_header = self.post_state.column_ids.get_column_header_by_id(sheet_index, column_id)
        transpiled_column_header = column_header_to_transpiled_code(column_header)
        
        na_position_string = 'first' if sort_direction == ASCENDING else 'last'
        
        return [
            f'{df_name} = {df_name}.sort_values(by={transpiled_column_header}, ascending={sort_direction == ASCENDING}, na_position=\'{na_position_string}\')', 
        ]