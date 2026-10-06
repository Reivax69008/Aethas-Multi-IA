from pydantic import BaseModel, EmailStr

class AdminCreate(BaseModel):
    email: EmailStr
    username: str
    password: str