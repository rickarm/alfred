"""Alfred skill registry — registers all available skills."""

from .registry import SkillRegistry
from .things import ThingsSkill
from .checkout import CheckoutSkill

registry = SkillRegistry()
registry.register(ThingsSkill())
registry.register(CheckoutSkill())

__all__ = ["registry"]
