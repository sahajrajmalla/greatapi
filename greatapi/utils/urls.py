import inspect

def get_route_app(class_name):
    module_path = inspect.getmodule(class_name).__name__
    split_by_dot = module_path.split('.')
    if split_by_dot[-1] == 'admin':
        return split_by_dot[-2]
    else:
        return split_by_dot[-1]


def get_route_dict(REGISTERED_ADMINS: list) -> dict:
    registered_admins = {}

    for admin_class in REGISTERED_ADMINS:
        app_name = get_route_app(admin_class)
        route_url = admin_class.__tablename__.lower()
        if app_name in registered_admins.keys():
            registered_admins[app_name].update({route_url: admin_class})
        else:
            registered_admins[app_name] = {route_url: admin_class}
    
    return registered_admins