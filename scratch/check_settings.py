from app.config import settings

print("Loaded Settings:")
print(f"  DB Server Name: '{settings.sfera.db_server_name}'")
print(f"  DB Name:        '{settings.sfera.db_name}'")
print(f"  Operator:       '{settings.sfera.sfera_operator}'")
print(f"  Operator Haslo: '{settings.sfera.sfera_operator_password}'")
