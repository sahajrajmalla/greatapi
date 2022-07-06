from greatapi.db.database import engine
import sqlalchemy


def fetch_table_data(TABLE_CLASS):
    query = sqlalchemy.select(TABLE_CLASS)
    result = engine.execute(query).fetchall()
    result_dict = [record._mapping for record in result]
    return result_dict

def fetch_app_list(admin_models):
    return [key for key in admin_models.keys()]

def fetch_admin_by_app(admin_models, app_name):
    return [key for key in admin_models[app_name]]