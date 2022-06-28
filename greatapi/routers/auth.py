from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from greatapi.db.database import get_db
from greatapi.db.models.user import User
from greatapi.repositories.auth.hashing import Hash
from greatapi.repositories.auth.jwt_token import create_access_token
from greatapi.schemas.auth import LoginSchema
from sqlalchemy.orm import Session

router = APIRouter(prefix="/login", tags=["Authentication"])


@router.post("/")
def login(request: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == request.username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Invalid Credentials")

    if not Hash.verify(user.password, request.password):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Incorrect Password")

    # Generate a JWT token and return
    access_token = create_access_token(data={"sub": user.email})

    return {"access_token": access_token, "token_type": "bearer"}
