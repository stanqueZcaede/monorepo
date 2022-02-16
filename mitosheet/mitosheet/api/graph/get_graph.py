import json
import pandas as pd
from typing import Any, Dict, List
from mitosheet.api.graph.column_summary_graph import get_column_summary_graph
from mitosheet.types import ColumnHeader
import plotly.express as px
import plotly.graph_objects as go
from mitosheet.api.graph.plotly_express_graphs import (
    get_plotly_express_graph,
    get_plotly_express_graph_code,
)
from mitosheet.api.graph.graph_utils import (
    SUMMARY_STAT,
    get_html_and_script_from_figure,
)
from mitosheet.errors import get_recent_traceback
from mitosheet.mito_analytics import log_recent_error
from mitosheet.steps_manager import StepsManager


def get_graph(event: Dict[str, Any], steps_manager: StepsManager) -> str:
    """
    Creates a graph of the passed parameters, and sends it back as a PNG
    string to the frontend for display.

    {
        graph_creation: {
            graph_type: GraphType,
            sheet_index: int
            x_axis_column_ids: ColumnID[],
            y_axis_column_ids: ColumnID[],
            color: (optional) {type: 'variable', columnID: columnID} | {type: 'constant', color_mapping: Record<ColumnID, string>}

            Note: Color is not in the styles object because it can either be a variable or a discrete color.
            Color as a variable does not belong in the style object. However, I want to keep the variable
            and constant color together so we can ensure through the type system that only one can be set at a time.
        }
        graph_rendering: {
            height: int representing the div width
            width: int representing the div width
        }
    }
    """
    # Get graph type
    graph_type = event["graph_creation"]["graph_type"]
    sheet_index = event["graph_creation"]["sheet_index"]

    # Get the x axis params, if they were provided
    x_axis_column_ids = (
        event["graph_creation"]["x_axis_column_ids"]
        if event["graph_creation"]["x_axis_column_ids"] is not None
        else []
    )
    x_axis_column_headers = steps_manager.curr_step.get_column_headers_by_ids(
        sheet_index, x_axis_column_ids
    )

    # Get the y axis params, if they were provided
    y_axis_column_ids = (
        event["graph_creation"]["y_axis_column_ids"]
        if event["graph_creation"]["y_axis_column_ids"] is not None
        else []
    )
    y_axis_column_headers = steps_manager.curr_step.get_column_headers_by_ids(
        sheet_index, y_axis_column_ids
    )

    # Find the height and the width, defaulting to fill whatever container its in
    graph_rendering_keys = event["graph_rendering"].keys()
    height = (
        event["graph_rendering"]["height"]
        if "height" in graph_rendering_keys
        else "100%"
    )
    width = (
        event["graph_rendering"]["width"] if "width" in graph_rendering_keys else "100%"
    )

    # Create a copy of the dataframe, just for safety.
    df: pd.DataFrame = steps_manager.dfs[sheet_index].copy()
    df_name: str = steps_manager.curr_step.df_names[sheet_index]

    # Handle the graphs in alphabetical order
    if graph_type == SUMMARY_STAT:
        # We handle summary stats separately from the histogram, for now, because
        # we only let the user use a histogram with all numeric data, whereas the column
        # summary stats may not be all numeric data.
        fig = get_column_summary_graph(df, x_axis_column_headers)
        generation_code = ""
    else:
        fig = get_plotly_express_graph(
            graph_type, df, x_axis_column_headers, y_axis_column_headers
        )
        generation_code = get_plotly_express_graph_code(
            graph_type, df, df_name, x_axis_column_headers, y_axis_column_headers
        )

    # Get rid of some of the default white space
    fig.update_layout(
        margin=dict(
            l=0,
            r=0,
            t=30,
            b=30,
        )
    )

    return_object = get_html_and_script_from_figure(fig, height, width)

    return_object["generation_code"] = generation_code

    return json.dumps(return_object)
