import random
import re
from collections import Counter


SEED_INPUT = """
If generation occurs entirely within LLM (without external translators), you control the randomness by narrowing the area from which the model extracts associations.
"""


def normalize(text):
    text = text.lower()
    text = re.sub(r"[^a-zа-яё0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_tokens(seed_input):
    # Если передали список строк
    if isinstance(seed_input, list):
        text = " ".join(seed_input)

    # Если передали одну строку
    elif isinstance(seed_input, str):
        text = seed_input

    else:
        raise TypeError("SEED_INPUT должен быть строкой или списком строк")

    tokens = normalize(text).split()

    stopwords = {
        "vs", "the", "a", "an", "and", "or"
    }

    tokens = [t for t in tokens if t not in stopwords]

    if not tokens:
        raise ValueError(
            "После обработки SEED_INPUT не осталось слов. "
            "Проверь входную строку или stopwords."
        )

    return tokens


TOKENS = extract_tokens(SEED_INPUT)
TOKEN_COUNTS = Counter(TOKENS)


def choose_token():
    """
    Чаще выбирает слова, которые чаще встречались во входном наборе.
    """
    tokens = list(TOKEN_COUNTS.keys())
    weights = list(TOKEN_COUNTS.values())
    return random.choices(tokens, weights=weights, k=1)[0]


def mutate_word(word):
    """
    Лёгкая мутация слова, чтобы получать panini -> paninix, samsung -> samsun.
    """
    if len(word) <= 3:
        return word

    letters = "abcdefghijklmnopqrstuvwxyz"
    operation = random.choice(["keep", "replace", "drop", "add"])

    if operation == "keep":
        return word

    if operation == "replace":
        i = random.randrange(len(word))
        return word[:i] + random.choice(letters) + word[i + 1:]

    if operation == "drop":
        i = random.randrange(len(word))
        return word[:i] + word[i + 1:]

    if operation == "add":
        i = random.randrange(len(word) + 1)
        return word[:i] + random.choice(letters) + word[i:]

    return word


def base_word():
    return mutate_word(choose_token())


def make_noun():
    word = base_word()

    endings = [
        "", "", "",
        "ness", "ment", "tion", "ism", "er", "ing"
    ]

    # Не добавляем суффиксы к числам
    if word.isdigit():
        return word

    ending = random.choice(endings)

    if word.endswith(ending):
        return word

    return word + ending


def make_verb():
    word = base_word()

    if word.isdigit():
        word = choose_token()

    endings = [
        "s", "ed", "ing", "izes", "ized", "ify", "ifies"
    ]

    # calculator -> calculatored, panini -> paninized
    if word.endswith("e"):
        return word + random.choice(["s", "d", "ing"])

    return word + random.choice(endings)


def make_adjective():
    word = base_word()

    if word.isdigit():
        word = choose_token()

    endings = [
        "", "", "",
        "ish", "al", "ic", "y", "ful", "less", "like"
    ]

    return word + random.choice(endings)


def make_adverb():
    word = make_adjective()

    if word.endswith("ly"):
        return word

    return word + "ly"


def make_year_phrase():
    years = [t for t in TOKENS if t.isdigit()]

    if not years:
        return ""

    year = random.choice(years)

    return random.choice([
        f"in {year}",
        f"after {year}",
        f"before {year}",
        f"around {year}",
    ])


def noun_phrase():
    patterns = [
        "{noun}",
        "the {noun}",
        "a {noun}",
        "the {adj} {noun}",
        "a {adj} {noun}",
        "{adj} {noun}",
    ]

    pattern = random.choice(patterns)

    return pattern.format(
        noun=make_noun(),
        adj=make_adjective()
    )


def verb_phrase():
    patterns = [
        "{verb}",
        "{verb} the {noun}",
        "{verb} a {noun}",
        "{verb} {adv}",
        "{verb} with the {noun}",
        "{verb} near the {noun}",
    ]

    pattern = random.choice(patterns)

    return pattern.format(
        verb=make_verb(),
        noun=make_noun(),
        adv=make_adverb()
    )


def prepositional_phrase():
    prep = random.choice([
        "in", "near", "after", "before", "around",
        "inside", "beside", "without", "through"
    ])

    return f"{prep} {noun_phrase()}"


def generate_sentence():
    patterns = [
        "{subj} {verb}.",
        "{subj} {verb} {prep}.",
        "{subj} {verb}, while {subj2} {verb2}.",
        "When {subj} {verb}, {subj2} {verb2}.",
        "Because {subj} {verb}, {subj2} {verb2} {prep}.",
        "{subj} was {adj} {prep}.",
        "{subj} became {adj} {year}.",
        "The {noun} of {noun2} {verb} {prep}.",
    ]

    pattern = random.choice(patterns)

    sentence = pattern.format(
        subj=noun_phrase(),
        subj2=noun_phrase(),
        verb=verb_phrase(),
        verb2=verb_phrase(),
        prep=prepositional_phrase(),
        adj=make_adjective(),
        noun=make_noun(),
        noun2=make_noun(),
        year=make_year_phrase()
    )

    sentence = re.sub(r"\s+", " ", sentence).strip()
    sentence = sentence[0].upper() + sentence[1:]

    return sentence


def generate_text(sentence_count=10):
    return " ".join(generate_sentence() for _ in range(sentence_count))


if __name__ == "__main__":
    print(generate_text(12))