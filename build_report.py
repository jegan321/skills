#!/usr/bin/env python3

# Build and open an HTML report summarizing the repository's available skills.

from html import escape
from pathlib import Path
import re
import webbrowser


REPO = Path(__file__).resolve().parent
REPORT = REPO / "tmp" / "skills.html"


def frontmatter_value(skill_file: Path, key: str) -> str | None:
    lines = skill_file.read_text().splitlines()
    if not lines or lines[0] != "---":
        return None

    prefix = f"{key}:"
    for line in lines[1:]:
        if line == "---":
            break
        if not line.startswith(prefix):
            continue

        value = line.removeprefix(prefix).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        return value

    return None


def metadata_value(skill_file: Path, key: str) -> str | None:
    lines = skill_file.read_text().splitlines()
    if not lines or lines[0] != "---":
        return None

    in_metadata = False
    prefix = f"{key}:"
    for line in lines[1:]:
        if line == "---":
            break
        if line == "metadata:":
            in_metadata = True
            continue
        if line and not line[0].isspace():
            in_metadata = False
        if not in_metadata or not line.lstrip().startswith(prefix):
            continue

        value = line.lstrip().removeprefix(prefix).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        return value

    return None


def skill_body(skill_file: Path) -> str:
    lines = skill_file.read_text().splitlines()
    if lines and lines[0] == "---":
        try:
            lines = lines[lines.index("---", 1) + 1 :]
        except ValueError:
            pass
    return "\n".join(lines).strip()


def render_inline(text: str) -> str:
    code_spans: list[str] = []

    def stash_code(match: re.Match[str]) -> str:
        code_spans.append(match.group(1))
        return f"\x00CODE{len(code_spans) - 1}\x00"

    text = re.sub(r"`([^`]+)`", stash_code, text)
    rendered = escape(text)
    rendered = re.sub(
        r"\[([^]]+)]\(([^)]+)\)",
        r'<a href="\2">\1</a>',
        rendered,
    )
    rendered = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", rendered)
    rendered = re.sub(r"(?<!\*)\*([^*]+)\*", r"<em>\1</em>", rendered)
    rendered = re.sub(r"_([^_]+)_", r"<em>\1</em>", rendered)

    for index, code in enumerate(code_spans):
        rendered = rendered.replace(
            f"\x00CODE{index}\x00", f"<code>{escape(code)}</code>"
        )
    return rendered


def markdown_to_html(markdown: str) -> str:
    lines = markdown.splitlines()
    rendered: list[str] = []
    index = 0

    while index < len(lines):
        line = lines[index]

        if not line.strip():
            index += 1
            continue

        fence = re.match(r"^```([^ ]*)\s*$", line)
        if fence:
            language = fence.group(1)
            index += 1
            code_lines = []
            while index < len(lines) and not lines[index].startswith("```"):
                code_lines.append(lines[index])
                index += 1
            index += index < len(lines)
            language_class = f' class="language-{escape(language)}"' if language else ""
            rendered.append(
                f"<pre><code{language_class}>{escape(chr(10).join(code_lines))}</code></pre>"
            )
            continue

        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            level = len(heading.group(1))
            rendered.append(f"<h{level}>{render_inline(heading.group(2))}</h{level}>")
            index += 1
            continue

        wrapper = re.fullmatch(r"<([a-zA-Z][\w-]*)>", line.strip())
        if wrapper:
            rendered.append(
                f'<div class="directive" data-label="{escape(wrapper.group(1))}">'
            )
            index += 1
            continue
        if re.fullmatch(r"</[a-zA-Z][\w-]*>", line.strip()):
            rendered.append("</div>")
            index += 1
            continue

        if (
            line.strip().startswith("|")
            and index + 1 < len(lines)
            and re.fullmatch(r"\s*\|?[\s:|-]+\|?\s*", lines[index + 1])
        ):
            headers = [cell.strip() for cell in line.strip().strip("|").split("|")]
            index += 2
            rows = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                rows.append(
                    [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
                )
                index += 1
            header_html = "".join(f"<th>{render_inline(cell)}</th>" for cell in headers)
            rows_html = "".join(
                "<tr>"
                + "".join(f"<td>{render_inline(cell)}</td>" for cell in row)
                + "</tr>"
                for row in rows
            )
            rendered.append(
                f"<div class=\"table-wrap\"><table><thead><tr>{header_html}</tr></thead>"
                f"<tbody>{rows_html}</tbody></table></div>"
            )
            continue

        list_match = re.match(r"^(?:[-*+] |(\d+)\. )(.+)$", line)
        if list_match:
            ordered = list_match.group(1) is not None
            tag = "ol" if ordered else "ul"
            items = []
            while index < len(lines):
                current = re.match(r"^(?:[-*+] |(\d+)\. )(.+)$", lines[index])
                if not current or (current.group(1) is not None) != ordered:
                    if (
                        not lines[index].strip()
                        and index + 1 < len(lines)
                        and re.match(r"^(?:[-*+] |\d+\. )", lines[index + 1])
                    ):
                        index += 1
                        continue
                    break
                item = current.group(2)
                task = re.match(r"^\[([ xX])]\s+(.+)$", item)
                if task:
                    checked = " checked" if task.group(1).lower() == "x" else ""
                    items.append(
                        f'<li class="task"><input type="checkbox" disabled{checked}>'
                        f"{render_inline(task.group(2))}</li>"
                    )
                else:
                    items.append(f"<li>{render_inline(item)}</li>")
                index += 1
            rendered.append(f"<{tag}>{''.join(items)}</{tag}>")
            continue

        if line.startswith("> "):
            quote_lines = []
            while index < len(lines) and lines[index].startswith("> "):
                quote_lines.append(lines[index][2:])
                index += 1
            rendered.append(
                f"<blockquote>{render_inline(' '.join(quote_lines))}</blockquote>"
            )
            continue

        if re.fullmatch(r"\s*(?:---|___|\*\*\*)\s*", line):
            rendered.append("<hr>")
            index += 1
            continue

        paragraph = [line.strip()]
        index += 1
        while index < len(lines) and lines[index].strip():
            paragraph.append(lines[index].strip())
            index += 1
        rendered.append(f"<p>{render_inline(' '.join(paragraph))}</p>")

    return "\n".join(rendered)


def allows_implicit_invocation(config: Path) -> bool:
    if not config.is_file():
        return True

    in_policy = False
    for line in config.read_text().splitlines():
        if re.fullmatch(r"policy:\s*(?:#.*)?", line):
            in_policy = True
            continue
        if line and not line[0].isspace() and not line.startswith("#"):
            in_policy = False
        if in_policy and re.fullmatch(
            r"\s+allow_implicit_invocation:\s*true\s*(?:#.*)?", line
        ):
            return True

    return False


def render_skill(
    name: str,
    author: str,
    description: str,
    content: str,
    modal_id: str,
) -> str:
    return f"""\
        <button class="skill" type="button" data-modal="{modal_id}" aria-haspopup="dialog">
          <span class="skill-name">{escape(name)}</span>
          <span class="author">{escape(author)}</span>
          <span class="description">{escape(description)}</span>
          <span class="view-skill">View full skill <span aria-hidden="true">→</span></span>
        </button>
        <dialog class="skill-dialog" id="{modal_id}" aria-label="{escape(name)}">
          <div class="dialog-header">
            <div>
              <p class="eyebrow">Skill details</p>
              <p class="dialog-title">{escape(name)}</p>
            </div>
            <button class="close-dialog" type="button" data-close aria-label="Close">×</button>
          </div>
          <div class="skill-content">
{content}
          </div>
        </dialog>"""


def render_section(heading: str, skills: list[tuple[str, str, str, str]]) -> str:
    section_id = heading.lower().replace(" ", "-")
    cards = "\n".join(
        render_skill(*skill, f"{section_id}-{index}")
        for index, skill in enumerate(skills)
    )
    return f"""\
      <section>
        <div class="section-heading">
          <h2>{escape(heading)}</h2>
          <span>{len(skills)}</span>
        </div>
        <div class="skill-list">
{cards}
        </div>
      </section>"""


def render_report(
    implicit_skills: list[tuple[str, str, str, str]],
    explicit_skills: list[tuple[str, str, str, str]],
) -> str:
    sections = "\n".join(
        (
            render_section("Implicit skills", implicit_skills),
            render_section("Explicit skills", explicit_skills),
        )
    )
    return f"""\
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Skills report</title>
    <style>
      :root {{
        color-scheme: dark;
        font-family: Geist, "Geist Sans", Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        background: #000;
        color: #ededed;
        --background: #000;
        --surface: #0a0a0a;
        --surface-hover: #111;
        --surface-raised: #1a1a1a;
        --border: #262626;
        --border-hover: #525252;
        --text-primary: #ededed;
        --text-secondary: #a1a1a1;
        --text-tertiary: #737373;
        --accent: #52a8ff;
      }}
      * {{ box-sizing: border-box; }}
      html {{ background: var(--background); }}
      body {{ margin: 0; min-height: 100vh; background: var(--background); }}
      ::selection {{ background: #fff; color: #000; }}
      button {{ font: inherit; }}
      main {{ width: min(72rem, calc(100% - 2rem)); margin: 0 auto; padding: 5rem 0; }}
      header {{ margin-bottom: 4rem; }}
      h1 {{ margin: 0 0 .65rem; font-size: clamp(2.5rem, 7vw, 4.75rem); font-weight: 650; letter-spacing: -.065em; line-height: 1; }}
      header p {{ margin: 0; color: var(--text-secondary); font-size: 1rem; }}
      section + section {{ margin-top: 3rem; }}
      .section-heading {{ display: flex; align-items: center; gap: .75rem; margin-bottom: 1rem; }}
      h2 {{ margin: 0; font-size: 1.15rem; font-weight: 550; letter-spacing: -.02em; }}
      .section-heading span {{ min-width: 1.75rem; padding: .15rem .5rem; border: 1px solid var(--border); border-radius: 999px; background: var(--surface); color: var(--text-secondary); font-size: .75rem; font-weight: 600; text-align: center; }}
      .skill-list {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 28rem), 1fr)); gap: 1rem; }}
      .skill {{ display: flex; flex-direction: column; align-items: flex-start; min-height: 13rem; padding: 1.5rem; border: 1px solid var(--border); border-radius: .75rem; background: var(--surface); color: inherit; text-align: left; cursor: pointer; transition: background .15s ease, border-color .15s ease, transform .15s ease; }}
      .skill:hover {{ border-color: var(--border-hover); background: var(--surface-hover); transform: translateY(-2px); }}
      .skill:focus-visible {{ outline: 2px solid var(--text-primary); outline-offset: 3px; }}
      .skill-name {{ margin: 0 0 .3rem; font-size: 1rem; font-weight: 600; letter-spacing: -.01em; }}
      .author {{ margin: 0 0 1rem; color: var(--text-tertiary); font-size: .8rem; font-weight: 500; }}
      .description {{ color: var(--text-secondary); line-height: 1.55; }}
      .view-skill {{ margin-top: auto; padding-top: 1.35rem; color: var(--text-primary); font-size: .8rem; font-weight: 550; }}
      .view-skill span {{ display: inline-block; transition: transform .15s ease; }}
      .skill:hover .view-skill span {{ transform: translateX(3px); }}
      .skill-dialog {{ width: min(50rem, calc(100% - 2rem)); max-height: min(52rem, calc(100vh - 2rem)); padding: 0; border: 1px solid var(--border); border-radius: .75rem; background: var(--surface); color: var(--text-primary); box-shadow: 0 24px 80px rgb(0 0 0 / .8); }}
      .skill-dialog::backdrop {{ background: rgb(0 0 0 / .78); backdrop-filter: blur(6px); }}
      .dialog-header {{ position: sticky; top: 0; z-index: 1; display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding: 1rem 1.25rem; border-bottom: 1px solid var(--border); background: rgb(10 10 10 / .9); backdrop-filter: blur(12px); }}
      .eyebrow {{ margin: 0 0 .15rem; color: var(--text-tertiary); font-size: .68rem; font-weight: 650; letter-spacing: .1em; text-transform: uppercase; }}
      .dialog-title {{ margin: 0; font-weight: 600; }}
      .close-dialog {{ width: 2.25rem; height: 2.25rem; border: 1px solid var(--border); border-radius: .45rem; background: transparent; color: var(--text-secondary); font-size: 1.35rem; line-height: 1; cursor: pointer; transition: background .15s, color .15s, border-color .15s; }}
      .close-dialog:hover {{ border-color: var(--border-hover); background: var(--surface-raised); color: var(--text-primary); }}
      .close-dialog:focus-visible {{ outline: 2px solid var(--text-primary); outline-offset: 2px; }}
      .skill-content {{ padding: 1.5rem 1.5rem 2.5rem; line-height: 1.65; }}
      .skill-content h1, .skill-content h2, .skill-content h3 {{ line-height: 1.2; letter-spacing: -.02em; }}
      .skill-content h1 {{ margin: 0 0 1.5rem; font-size: 2rem; }}
      .skill-content h2 {{ margin: 2rem 0 .75rem; font-size: 1.35rem; }}
      .skill-content h3 {{ margin: 1.5rem 0 .65rem; font-size: 1.1rem; }}
      .skill-content p {{ margin: .8rem 0; }}
      .skill-content ul, .skill-content ol {{ padding-left: 1.5rem; }}
      .skill-content li + li {{ margin-top: .45rem; }}
      .skill-content a {{ color: var(--accent); text-underline-offset: .2em; }}
      .skill-content code {{ padding: .15rem .35rem; border: 1px solid var(--border); border-radius: .3rem; background: var(--surface-raised); font-size: .86em; }}
      .skill-content pre {{ overflow-x: auto; padding: 1rem; border: 1px solid var(--border); border-radius: .65rem; background: #050505; color: var(--text-primary); }}
      .skill-content pre code {{ padding: 0; background: transparent; color: inherit; }}
      .skill-content blockquote {{ margin: 1rem 0; padding: .1rem 1rem; border-left: 2px solid var(--border-hover); color: var(--text-secondary); }}
      .table-wrap {{ overflow-x: auto; }}
      table {{ width: 100%; border-collapse: collapse; font-size: .9rem; }}
      th, td {{ padding: .55rem .7rem; border: 1px solid var(--border); text-align: left; }}
      th {{ background: var(--surface-raised); }}
      .directive {{ margin: 1rem 0; padding: .25rem 1rem; border-left: 2px solid var(--border-hover); }}
      .task {{ list-style: none; margin-left: -1.5rem; }}
      .task input {{ margin-right: .5rem; }}
      @media (prefers-reduced-motion: reduce) {{
        .skill, .view-skill span {{ transition: none; }}
      }}
    </style>
  </head>
  <body>
    <main>
      <header>
        <h1>Skills report</h1>
        <p>{len(implicit_skills) + len(explicit_skills)} skills in this repository</p>
      </header>
{sections}
    </main>
    <script>
      document.querySelectorAll("[data-modal]").forEach((card) => {{
        card.addEventListener("click", () => {{
          document.getElementById(card.dataset.modal).showModal();
        }});
      }});

      document.querySelectorAll(".skill-dialog").forEach((dialog) => {{
        dialog.querySelector("[data-close]").addEventListener("click", () => dialog.close());
        dialog.addEventListener("click", (event) => {{
          if (event.target === dialog) dialog.close();
        }});
      }});
    </script>
  </body>
</html>
"""


def main() -> None:
    skill_files = sorted((REPO / "skills").rglob("SKILL.md"))
    implicit_skills = []
    explicit_skills = []

    for skill_file in skill_files:
        skill_dir = skill_file.parent
        name = frontmatter_value(skill_file, "name") or skill_dir.name
        description = (
            frontmatter_value(skill_file, "description")
            or "(No description provided)"
        )
        author = metadata_value(skill_file, "original-author") or "Unknown author"
        content = markdown_to_html(skill_body(skill_file))
        skill = (name, author, description, content)
        category = (
            implicit_skills
            if allows_implicit_invocation(skill_dir / "agents" / "openai.yaml")
            else explicit_skills
        )
        category.append(skill)

    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(
        render_report(implicit_skills, explicit_skills),
        encoding="utf-8",
    )
    webbrowser.open(REPORT.as_uri())


if __name__ == "__main__":
    main()
