import base64
import random

from jinja2 import Environment
from names_generator import generate_name


def random_name(seed: str = "") -> str:
    return generate_name(style="underscore", seed=seed).replace("_", "")


def random_number(from_number: int, to_number: int, seed: str = "") -> str:
    random.seed(seed)
    return str(random.randint(from_number, to_number))


def base64_encode(value: str) -> str:
    return base64.b64encode(value.encode()).decode()


def render(template, func_dict):
    env = Environment()
    jinja_template = env.from_string(template)
    jinja_template.globals.update(func_dict)
    template_string = jinja_template.render()
    return template_string


def generate_session(email: str, game: str, task: str) -> dict:
    from common.pytest import get_session_template

    session = get_session_template(game, task)

    student_id = email.split("@")[0]
    func_dict = {
        "student_id": lambda: student_id,
        "random_name": lambda: random_name(student_id),
        "random_number": lambda f, to: random_number(f, to, student_id),
        "base64_encode": base64_encode,
    }

    session = {
        k: render(v, func_dict) if isinstance(v, str) else v for k, v in session.items()
    }

    return session
