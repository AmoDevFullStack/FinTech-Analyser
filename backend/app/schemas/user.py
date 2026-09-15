from app.models.user import User


def user_dict(user: User) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "currency": user.currency,
        "timezone": user.timezone,
    }
