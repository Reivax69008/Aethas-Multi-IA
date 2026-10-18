import glob
import py_compile
import re
import sys

def main():
    for py_file in glob.glob("backend/*.py"):
        try:
            py_compile.compile(py_file, doraise=True)
        except Exception as e:
            print(f"ERREUR PYTHON dans {py_file} : {e}")
            sys.exit(1)

    tags = ["html", "head", "body", "script", "style", "div", "main", "aside", "header", "table", "select", "textarea"]
    for html_file in glob.glob("frontend/*.html"):
        with open(html_file, "r", encoding="utf-8") as f:
            content = f.read()
        for tag in tags:
            opens = len(re.findall(rf"<{tag}(?=[\s>])", content))
            closes = len(re.findall(rf"</{tag}\s*>", content))
            if opens != closes:
                print(f"ERREUR HTML dans {html_file} : balise <{tag}> non equilibree ({opens} ouv. vs {closes} ferm.)")
                sys.exit(1)

    print("OK : Code Backend (.py) + Frontend (.html) 100% valides, pret pour Gitea !")

if __name__ == "__main__":
    main()