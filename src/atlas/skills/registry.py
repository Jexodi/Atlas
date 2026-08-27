from atlas.skills.base import Skill


class SkillRegistry:

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(
        self,
        skill: Skill,
    ) -> None:

        if skill.name in self._skills:
            raise ValueError(
                f"Le Skill '{skill.name}' est déjà enregistré."
            )

        self._skills[skill.name] = skill

    def unregister(
        self,
        skill_name: str,
    ) -> None:

        self._skills.pop(
            skill_name,
            None,
        )

    def get(
        self,
        skill_name: str,
    ) -> Skill | None:

        return self._skills.get(skill_name)

    def exists(
        self,
        skill_name: str,
    ) -> bool:

        return skill_name in self._skills

    def list_skills(
        self,
    ) -> list[Skill]:

        return list(
            self._skills.values()
        )