from pydantic import BaseModel

class UserSchema(BaseModel):
	name: str
	email: str

	class Config():
		orm_mode = True

class UserType(UserSchema):
	password: str

class ShowUser(BaseModel):
	name: str
	email: str

	class Config():
		orm_mode = True