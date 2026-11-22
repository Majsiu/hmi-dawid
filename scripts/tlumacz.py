#!/usr/bin/env python3
"""Automatyczne tłumaczenie wydarzeń PL -> EN dla knhmi.pl.

Dla każdego pliku w _wydarzenia/ uzupełnia PUSTE pola title_en i text_en
tłumaczeniem z title i text. Pól EN wpisanych ręcznie nie rusza.
Żeby przetłumaczyć wydarzenie ponownie, wyczyść jego pola EN w panelu.

Tłumacz (wybierany po tym, który klucz jest ustawiony w Secrets repozytorium):
  DEEPL_API_KEY  – DeepL API Free (najlepsza jakość)
  GEMINI_API_KEY – Google Gemini (darmowy klucz z aistudio.google.com)
"""
import glob, json, os, re, sys, time, urllib.request, urllib.parse
import yaml

POLA = [("title", "title_en"), ("text", "text_en")]
FM = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.S)


def tlumacz_deepl(tekst, klucz):
    host = "api-free.deepl.com" if klucz.endswith(":fx") else "api.deepl.com"
    dane = urllib.parse.urlencode({"text": tekst, "source_lang": "PL", "target_lang": "EN-GB"}).encode()
    req = urllib.request.Request(f"https://{host}/v2/translate", data=dane,
                                 headers={"Authorization": f"DeepL-Auth-Key {klucz}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)["translations"][0]["text"]


def tlumacz_gemini(tekst, klucz):
    model = os.environ.get("GEMINI_MODEL") or "gemini-flash-latest"
    polecenie = (
        "Translate the following Polish text into natural British English for the website of a "
        "university student research club (Koło Naukowe HMI, Gdynia Maritime University). "
        "Keep personal names, project names, emojis, hashtags and @handles unchanged. "
        "Return only the translation, with no comments or quotation marks.\n\n" + tekst
    )
    body = json.dumps({"contents": [{"parts": [{"text": polecenie}]}]}).encode()
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=body, headers={"Content-Type": "application/json", "x-goog-api-key": klucz})
    with urllib.request.urlopen(req, timeout=120) as r:
        odp = json.load(r)
    return "".join(p.get("text", "") for p in odp["candidates"][0]["content"]["parts"]).strip()


def wybierz_tlumacza():
    if os.environ.get("DEEPL_API_KEY"):
        return lambda t: tlumacz_deepl(t, os.environ["DEEPL_API_KEY"]), "DeepL"
    if os.environ.get("GEMINI_API_KEY"):
        return lambda t: tlumacz_gemini(t, os.environ["GEMINI_API_KEY"]), "Gemini"
    return None, None


def main(folder="_wydarzenia"):
    tlumacz, nazwa = wybierz_tlumacza()
    if not tlumacz:
        print("Brak klucza DEEPL_API_KEY ani GEMINI_API_KEY w Secrets – pomijam tłumaczenie.")
        return 0
    zmienione = 0
    for sciezka in sorted(glob.glob(os.path.join(folder, "*.md"))):
        tresc = open(sciezka, encoding="utf-8").read()
        m = FM.match(tresc)
        if not m:
            continue
        dane = yaml.safe_load(m.group(1)) or {}
        zmiana = False
        for pl, en in POLA:
            if dane.get(pl) and not str(dane.get(en) or "").strip():
                for proba in range(3):
                    try:
                        dane[en] = tlumacz(str(dane[pl]).strip())
                        break
                    except Exception as e:  # limit zapytań, chwilowy błąd sieci
                        print(f"  błąd ({e}), ponawiam…")
                        time.sleep(10 * (proba + 1))
                else:
                    print(f"  NIE udało się przetłumaczyć {en} w {sciezka}")
                    continue
                zmiana = True
                print(f"{nazwa}: {os.path.basename(sciezka)} -> {en}")
        if zmiana:
            fm = yaml.safe_dump(dane, allow_unicode=True, sort_keys=False, width=10000)
            with open(sciezka, "w", encoding="utf-8") as f:
                f.write("---\n" + fm + "---\n" + m.group(2))
            zmienione += 1
    print(f"Przetłumaczone pliki: {zmienione}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
