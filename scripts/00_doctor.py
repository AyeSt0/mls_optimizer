
import importlib.util, os, sys

def check_pkg(name):
    return importlib.util.find_spec(name) is not None

def main():
    print("[doctor] Python:", sys.version)
    for n in ["openpyxl","pandas","openai","tqdm","pyyaml"]:
        print(f"[doctor] dep {n}: {'OK' if check_pkg(n) else 'MISSING'}")
    for env in ["OPENAI_API_KEY","DEEPSEEK_API_KEY"]:
        v = os.environ.get(env)
        print(f"[doctor] env {env}: {'set' if v else 'missing'}")
    print("[doctor] If deps missing, run: pip install pandas openpyxl openai tqdm pyyaml")
if __name__ == "__main__":
    main()
