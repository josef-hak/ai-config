# Usage

~~~bash
rm -rf ./ai-config-wc
git clone https://github.com/josef-hak/ai-config.git ./ai-config-wc
cp ./ai-config-wc/claude/CLAUDE.md ~/.claude/CLAUDE.md
cp ./ai-config-wc/claude/settings.json ~/.claude/settings.json
mkdir -p ~/.claude/skills
rsync -a ./ai-config-wc/skills/ ~/.claude/skills/
~~~
