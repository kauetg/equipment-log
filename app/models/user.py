from bson import ObjectId
from bson.errors import InvalidId
from flask_login import UserMixin


class User(UserMixin):
    def __init__(self, doc):
        self.id = str(doc["_id"])
        self.name = doc["name"]
        self.email = doc["email"]
        self.password_hash = doc["password_hash"]
        self.household_id = doc["household_id"]
        self.role = doc.get("role")

    @staticmethod
    def get(db, user_id):
        try:
            doc = db.users.find_one({"_id": ObjectId(user_id)})
        except InvalidId:
            return None
        return User(doc) if doc else None

    @staticmethod
    def get_by_email(db, email):
        doc = db.users.find_one({"email": email})
        return User(doc) if doc else None
