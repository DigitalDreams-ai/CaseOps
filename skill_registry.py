"""Skill registry for lazy-loading and caching skill metadata.

Loads all skills once at Flask app startup. Subsequent lookups return cached
metadata and body without re-reading files.
"""

import re
from pathlib import Path
from typing import Any


class SkillRegistry:
    """Central registry for skill metadata and content.

    Loads skill definitions from SKILL.md files once, caches results.
    Supports multiple skill directories (e.g., skills/, .claude/skills/).
    """

    def __init__(self):
        self.skills: dict[str, dict[str, Any]] = {}
        self._loaded = False

    def load_all_skills(self, *skill_dirs: Path) -> None:
        """Load all skills from the given directories.

        Args:
            *skill_dirs: Variable number of Path objects pointing to skill root directories.
                        Example: load_all_skills(ROOT / "skills", ROOT / ".claude" / "skills")

        Returns:
            None. Skills are cached in self.skills dict, including bundled guides.
        """
        if self._loaded:
            return  # Skip if already loaded

        for skill_dir in skill_dirs:
            if not skill_dir.exists():
                continue

            # Iterate over subdirectories in skill_dir
            for skill_path in skill_dir.iterdir():
                if not skill_path.is_dir():
                    continue

                skill_md = skill_path / "SKILL.md"
                if not skill_md.exists():
                    continue

                skill_name = skill_path.name
                try:
                    skill_data = self._parse_skill(skill_md)

                    # Bundle guides from references/ subdirectory (if it exists)
                    references_dir = skill_path / "references"
                    guides = {}
                    if references_dir.exists():
                        for guide_file in references_dir.glob("*.md"):
                            guide_name = guide_file.stem
                            try:
                                guides[guide_name] = guide_file.read_text(encoding="utf-8")
                            except Exception as e:
                                print(f"Warning: Failed to load guide {guide_name} for skill {skill_name}: {e}")
                    skill_data["guides"] = guides

                    self.skills[skill_name] = skill_data
                except Exception as e:
                    print(f"Warning: Failed to load skill {skill_name} from {skill_md}: {e}")

        self._loaded = True

    def _parse_skill(self, skill_md_path: Path) -> dict[str, Any]:
        """Parse a SKILL.md file into metadata and body.

        SKILL.md format:
        ---
        name: skill-name
        description: ...
        compatibility: ...
        ---

        [Body content]

        Returns:
            dict with keys: name, description, compatibility, body, path
        """
        content = skill_md_path.read_text(encoding="utf-8")

        # Extract frontmatter (YAML between --- delimiters)
        frontmatter_match = re.match(r"^---\n(.*?)\n---\n(.*)", content, re.DOTALL)
        if not frontmatter_match:
            raise ValueError(f"No frontmatter found in {skill_md_path}")

        frontmatter_text = frontmatter_match.group(1)
        body = frontmatter_match.group(2)

        # Parse YAML-ish frontmatter (simple key: value parsing)
        metadata = {}
        for line in frontmatter_text.split("\n"):
            if ":" in line:
                key, val = line.split(":", 1)
                metadata[key.strip()] = val.strip()

        return {
            "name": metadata.get("name", skill_md_path.parent.name),
            "description": metadata.get("description", ""),
            "compatibility": metadata.get("compatibility", ""),
            "body": body.strip(),
            "path": str(skill_md_path),
        }

    def get_skill(self, skill_name: str) -> dict[str, Any] | None:
        """Get cached skill data by name.

        Args:
            skill_name: Name of the skill (e.g., 'caseops-pipeline')

        Returns:
            dict with skill metadata and body, or None if not found.
        """
        return self.skills.get(skill_name)

    def get_skill_body(self, skill_name: str) -> str | None:
        """Get just the body content of a skill.

        Args:
            skill_name: Name of the skill

        Returns:
            The body content (without frontmatter), or None if not found.
        """
        skill = self.get_skill(skill_name)
        return skill["body"] if skill else None

    def list_skills(self) -> list[str]:
        """List all loaded skill names."""
        return sorted(self.skills.keys())

    def skill_count(self) -> int:
        """Return the number of loaded skills."""
        return len(self.skills)

    def get_guide(self, skill_name: str, guide_name: str) -> str | None:
        """Get a bundled guide content by skill name and guide name.

        Args:
            skill_name: Name of the skill (e.g., 'caseops-pipeline')
            guide_name: Name of the guide without .md extension (e.g., 'workflow')

        Returns:
            Guide content as string, or None if not found.
        """
        skill = self.get_skill(skill_name)
        if not skill:
            return None
        guides = skill.get("guides", {})
        return guides.get(guide_name)

    def list_guides(self, skill_name: str) -> list[str]:
        """List all guide names for a skill.

        Args:
            skill_name: Name of the skill

        Returns:
            List of guide names (without .md extension), or empty list if skill not found.
        """
        skill = self.get_skill(skill_name)
        if not skill:
            return []
        return sorted(skill.get("guides", {}).keys())
