from greatapi.utils.cbv import cbv
from greatapi.utils.inferring_router import InferringRouter

router = InferringRouter()

class AdminSite:
    @router.get("/somewhere")
    def bar(self) -> dict:
        get_name = self.json_models.get("sahaj").name
        return {"My name is": get_name}