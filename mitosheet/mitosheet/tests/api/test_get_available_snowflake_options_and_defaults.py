import json
import os
from mitosheet.api.get_available_snowflake_options_and_defaults import get_available_snowflake_options_and_defaults
from mitosheet.api.get_validate_snowflake_credentials import get_validate_snowflake_credentials
from mitosheet.tests.test_utils import create_mito_wrapper
from mitosheet.tests.decorators import python_post_3_6_only, requires_snowflake_dependencies_and_credentials

PYTEST_SNOWFLAKE_USERNAME = os.getenv('PYTEST_SNOWFLAKE_USERNAME')
PYTEST_SNOWFLAKE_PASSWORD = os.getenv('PYTEST_SNOWFLAKE_PASSWORD')
PYTEST_SNOWFLAKE_ACCOUNT = os.getenv('PYTEST_SNOWFLAKE_ACCOUNT')

TEST_SNOWFLAKE_CREDENTIALS = {
    'type': 'username/password', 
    'username': PYTEST_SNOWFLAKE_USERNAME, 
    'password': PYTEST_SNOWFLAKE_PASSWORD, 
    'account': PYTEST_SNOWFLAKE_ACCOUNT
}

TEST_DEFAULT_SNOWFLAKE_CONNECTION = {
    'warehouse': None, 
    'database': None, 
    'schema': None,
    'table': None,
}

@requires_snowflake_dependencies_and_credentials
@python_post_3_6_only
def test_integration_success():
    mito = create_mito_wrapper()

    table_loc_and_warehouse = {
        'warehouse': 'COMPUTE_WH',
        'database': 'PYTESTDATABASE',
        'schema': 'PYTESTSCHEMA',
        'table_or_view': 'SIMPLE_PYTEST_TABLE',
    }

    params = {
        'table_loc_and_warehouse': table_loc_and_warehouse
    }

    get_validate_snowflake_credentials(TEST_SNOWFLAKE_CREDENTIALS, mito.mito_backend.steps_manager)

    response = get_available_snowflake_options_and_defaults(params, mito.mito_backend.steps_manager)

    expected_return = json.dumps({
        'type': 'success',    
        'config_options': {
                'warehouses': ['COMPUTE_WH'],    
                'databases': ['PYTESTDATABASE', 'SNOWFLAKE', 'SNOWFLAKE_SAMPLE_DATA'],    
                'schemas': ['INFORMATION_SCHEMA', 'PYTESTSCHEMA'],
                'tables_and_views': ["COLUMNHEADER_TEST", "NOROWS", "SIMPLE_PYTEST_TABLE", "TYPETEST", "TYPETEST_SIMPLE", "SIMPLE_PYTEST_TABLE_VIEW"],
                'columns': ['COLUMNA', 'COLUMNB']
        },
        'default_values': table_loc_and_warehouse
    })

    assert expected_return == response
