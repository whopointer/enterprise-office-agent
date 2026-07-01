from dataclasses import dataclass
from pathlib import Path
import re
import yaml


@dataclass
class SkillMetadata:
    name: str
    description: str
    path: str


class FileSkillsLoader:
    def __init__(self, skills_dir: str):
        self.skills_dir = Path(skills_dir)

    def load(self) -> list[SkillMetadata]:
        skills: list[SkillMetadata] = []

        if not self.skills_dir.exists():
            return skills

        for skill_dir in self.skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue

            skill_file = skill_dir / "SKILL.md"
            if not skill_file.is_file():
                continue

            skill = self._parse_skill_file(skill_file)
            if skill is not None:
                skills.append(skill)

        return skills

    def _parse_skill_file(self, skill_file: Path) -> SkillMetadata | None:
        content = skill_file.read_text(encoding="utf-8")

        match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
        if not match:
            return None

        frontmatter = yaml.safe_load(match.group(1)) or {}

        name = str(frontmatter.get("name", "")).strip()
        description = str(frontmatter.get("description", "")).strip()

        if not name or not description:
            return None

        return SkillMetadata(
            name=name,
            description=description,
            path=str(skill_file.resolve()),
        )


def format_skills_prompt(skills: list[SkillMetadata]) -> str:
    if not skills:
        return ""

    lines = [
        "## Skills",
        "",
        "You have access to the following skills.",
        "Use a skill only when the user's task matches its description.",
        "",
    ]

    for skill in skills:
        lines.append(f"- **{skill.name}**: {skill.description}")
        lines.append(f"  Read `{skill.path}` for full instructions.")

    return "\n".join(lines)


class SkillsMiddleware:
    def __init__(self, skills_dir: str):
        self.loader = FileSkillsLoader(skills_dir)

    def before_agent(self, state: dict) -> None:
        if "skills_metadata" in state:
            return

        state["skills_metadata"] = self.loader.load()

    def modify_system_prompt(self, system_prompt: str, state: dict) -> str:
        skills = state.get("skills_metadata", [])
        skills_prompt = format_skills_prompt(skills)

        if not skills_prompt:
            return system_prompt

        return system_prompt + "\n\n" + skills_prompt


if __name__ == "__main__":
    skills = FileSkillsLoader("skills").load()
    print(format_skills_prompt(skills) or "No skills found.")
