"""에이전트별 입구 파일이 core/ 와 어긋나지 않는지 검사한다 (사본 분기 방지)."""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class AdapterTests(unittest.TestCase):
    SKILLS = [".agents/skills/homepage-inspection/SKILL.md", ".claude/skills/homepage-inspection/SKILL.md"]

    def test_skill_frontmatter(self):
        for rel in self.SKILLS:
            text = read(rel)
            m = re.match(r"^---\nname: (.+)\ndescription: (.+)\n---\n", text)
            self.assertTrue(m, rel)
            self.assertEqual(m.group(1), os.path.basename(os.path.dirname(rel)))   # name == 폴더명
            self.assertLess(len(m.group(2)), 1024)

    def test_skill_copies_identical(self):
        self.assertEqual(read(self.SKILLS[0]), read(self.SKILLS[1]))

    def test_referenced_paths_exist(self):
        files = self.SKILLS + ["AGENTS.md", ".clinerules/homepage-inspection.md", "README.md"] + \
            [".agents/workflows/" + f for f in os.listdir(os.path.join(ROOT, ".agents", "workflows"))]
        pat = re.compile(r"`((?:core|scripts|docs|config\.example)/[\w./\-가-힣]+\.(?:md|py|json))`")
        for rel in files:
            for ref in pat.findall(read(rel)):
                self.assertTrue(os.path.exists(os.path.join(ROOT, ref)), "%s -> %s" % (rel, ref))

    def test_claude_md_imports_agents(self):
        self.assertEqual(read("CLAUDE.md").strip(), "@AGENTS.md")

    def test_no_stale_paths(self):
        for rel in self.SKILLS + ["AGENTS.md", ".clinerules/homepage-inspection.md"]:
            self.assertNotIn("references/", read(rel))


if __name__ == "__main__":
    unittest.main()
