from fastapi import APIRouter, Depends
from greatapi.db.models.user import User
from greatapi.repositories.auth.jwt_token import get_current_user

router = APIRouter(prefix="/index", tags=["Index"])


@router.get("/", response_model=str)
def index(current_user: User = Depends(get_current_user)):
    return "Hello World!"
