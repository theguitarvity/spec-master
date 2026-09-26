import _pathfix  # noqa: F401

import os
import shutil
import tempfile
import unittest

import ears


def _codes(result):
    return [h["code"] for h in result["hints"]]


class PatternTests(unittest.TestCase):
    CASES = [
        # (text, pattern, lang, expected clauses subset)
        ("The system shall log every request.", "ubiquitous", "en",
         {"system": "system", "response": "log every request"}),
        ("O sistema deve registrar cada requisição.", "ubiquitous", "pt",
         {"system": "sistema", "response": "registrar cada requisição"}),
        ("A API deverá responder em 200 ms", "ubiquitous", "pt", {"system": "API"}),
        ("When the user clicks Save, the editor shall persist the draft", "event", "en",
         {"trigger": "the user clicks Save", "system": "editor", "response": "persist the draft"}),
        ("Quando o usuário clicar em salvar, o editor deve persistir o rascunho.", "event", "pt",
         {"trigger": "o usuário clicar em salvar", "system": "editor", "response": "persistir o rascunho"}),
        ("While offline, the app shall queue changes;", "state", "en",
         {"state": "offline", "system": "app", "response": "queue changes"}),
        ("Enquanto o upload estiver em andamento, o sistema deve exibir o progresso", "state", "pt",
         {"state": "o upload estiver em andamento", "response": "exibir o progresso"}),
        ("If the password is wrong, then the system shall show an error!", "unwanted", "en",
         {"condition": "the password is wrong", "system": "system", "response": "show an error"}),
        ("Se a senha estiver incorreta, então o sistema deve exibir uma mensagem de erro.", "unwanted", "pt",
         {"condition": "a senha estiver incorreta", "system": "sistema"}),
        ("Where export is enabled, the system shall offer CSV download", "optional", "en",
         {"feature": "export is enabled", "response": "offer CSV download"}),
        ("Onde a exportação estiver habilitada, o sistema deve oferecer download em CSV", "optional", "pt",
         {"feature": "a exportação estiver habilitada"}),
    ]

    def test_each_pattern_en_and_pt(self):
        for text, pattern, lang, clauses in self.CASES:
            with self.subTest(text=text):
                result = ears.parse(text)
                self.assertEqual(result["pattern"], pattern)
                self.assertEqual(result["lang"], lang)
                for key, value in clauses.items():
                    self.assertEqual(result["clauses"][key], value)
                self.assertEqual(result["hints"], [])

    def test_complex_en_and_pt(self):
        en = ears.parse("While the vehicle is moving, when the driver presses the brake, "
                        "the controller shall engage ABS")
        self.assertEqual(en["pattern"], "complex")
        self.assertEqual(en["clauses"]["state"], "the vehicle is moving")
        self.assertEqual(en["clauses"]["trigger"], "the driver presses the brake")
        self.assertEqual([p["keyword"] for p in en["preconditions"]], ["while", "when"])

        pt = ears.parse("Enquanto o veículo estiver em movimento, quando o motorista pressionar o freio, "
                        "o controlador deve acionar o ABS.")
        self.assertEqual(pt["pattern"], "complex")
        self.assertEqual(pt["lang"], "pt")
        self.assertEqual(pt["clauses"]["system"], "controlador")

        optional_event = ears.parse("Where MFA is enabled, if the code expires, then the system shall ask again")
        self.assertEqual(optional_event["pattern"], "complex")
        self.assertEqual(optional_event["clauses"]["feature"], "MFA is enabled")
        self.assertEqual(optional_event["clauses"]["condition"], "the code expires")

    def test_case_insensitive_and_tolerant(self):
        result = ears.parse("  - [ ] AC-3: WHEN the timer expires,   THE scheduler SHALL retry.  ")
        self.assertEqual(result["pattern"], "event")
        self.assertEqual(result["clauses"]["system"], "scheduler")
        self.assertEqual(result["text"], "WHEN the timer expires, THE scheduler SHALL retry")

    def test_commas_inside_trigger_are_kept(self):
        result = ears.parse("When the user enters name, email and password, the system shall create the account")
        self.assertEqual(result["pattern"], "event")
        self.assertEqual(result["clauses"]["trigger"], "the user enters name, email and password")

    def test_missing_comma_still_classified_with_hint(self):
        result = ears.parse("When the user logs in the system shall greet them")
        self.assertEqual(result["pattern"], "event")
        self.assertEqual(result["clauses"]["trigger"], "the user logs in")
        self.assertIn("missing_comma", _codes(result))

    def test_unwanted_without_then_hints(self):
        result = ears.parse("If the disk is full, the system shall raise an alert")
        self.assertEqual(result["pattern"], "unwanted")
        self.assertIn("missing_then", _codes(result))


class HintTests(unittest.TestCase):
    def test_weak_modal_is_hint_not_match(self):
        for text, word in [("The system must encrypt data at rest", "must"),
                           ("Users should be able to reset their password", "should"),
                           ("When saved, the app will notify the owner", "will")]:
            with self.subTest(text=text):
                result = ears.parse(text)
                self.assertIsNone(result["pattern"])
                self.assertEqual(result["hints"][0]["code"], "weak_modal")
                self.assertEqual(result["hints"][0]["term"], word)

    def test_vague_terms_en_and_pt(self):
        en = ears.parse("The dashboard shall load fast and be user-friendly")
        self.assertEqual(en["pattern"], "ubiquitous")
        self.assertEqual(sorted(h["term"] for h in en["hints"] if h["code"] == "vague_term"),
                         ["fast", "user-friendly"])
        pt = ears.parse("O sistema deve ser rápido e amigável")
        self.assertEqual(pt["pattern"], "ubiquitous")
        self.assertEqual(sorted(h["term"] for h in pt["hints"] if h["code"] == "vague_term"),
                         ["amigável", "rápido"])

    def test_missing_system(self):
        result = ears.parse("shall export the report")
        self.assertIsNone(result["pattern"])
        self.assertIn("missing_system", _codes(result))
        result = ears.parse("When the user clicks export, shall download a CSV")
        self.assertIsNone(result["pattern"])
        self.assertIn("missing_system", _codes(result))

    def test_multiple_shall(self):
        result = ears.parse("The system shall log in the user and shall send an email")
        self.assertEqual(result["pattern"], "ubiquitous")
        self.assertIn("multiple_shall", _codes(result))

    def test_unknown_precondition(self):
        result = ears.parse("After login, the system shall show the dashboard")
        self.assertIsNone(result["pattern"])
        self.assertIn("unknown_precondition", _codes(result))

    def test_plain_text_and_empty(self):
        self.assertEqual(_codes(ears.parse("Invalid credentials show an error")), ["no_modal"])
        self.assertEqual(_codes(ears.parse("   ")), ["empty"])

    def test_mixed_language(self):
        result = ears.parse("Quando o pedido for pago, the system shall send a receipt")
        self.assertEqual(result["pattern"], "event")
        self.assertIn("mixed_language", _codes(result))


class ValidateTests(unittest.TestCase):
    CRITERIA = [
        "When the user submits the form, the system shall save it",
        "Invalid credentials show an error",
        "O sistema deve registrar auditoria",
    ]

    def test_non_strict_is_always_valid(self):
        result = ears.validate(self.CRITERIA)
        self.assertFalse(result["strict"])
        self.assertTrue(result["valid"])
        self.assertEqual((result["total"], result["ears"], result["non_ears"]), (3, 2, 1))
        self.assertAlmostEqual(result["coverage"], 0.6667)
        self.assertEqual([i["ears"] for i in result["items"]], [True, False, True])
        self.assertEqual([i["index"] for i in result["items"]], [0, 1, 2])

    def test_strict_fails_on_non_ears(self):
        self.assertFalse(ears.validate(self.CRITERIA, strict=True)["valid"])
        ok = ears.validate([self.CRITERIA[0], self.CRITERIA[2]], strict=True)
        self.assertTrue(ok["valid"])
        self.assertEqual(ok["coverage"], 1.0)

    def test_empty_and_dict_criteria(self):
        empty = ears.validate([], strict=True)
        self.assertEqual((empty["total"], empty["coverage"], empty["valid"]), (0, 1.0, True))
        result = ears.validate([{"text": "The API shall return JSON"}])
        self.assertEqual(result["items"][0]["pattern"], "ubiquitous")


class CheckStateTests(unittest.TestCase):
    STATE = {
        "features": [
            {"id": "a", "name": "A", "acceptance_criteria": [
                "When a job fails, the scheduler shall retry it", "Jobs are fast"]},
            {"id": "b", "name": "B", "acceptance_criteria": ["Se o token expirar, então a API deve retornar 401"]},
            {"id": "c", "name": "C"},
        ]
    }

    def test_all_features(self):
        result = ears.check_state(self.STATE)
        self.assertEqual([f["id"] for f in result["features"]], ["a", "b", "c"])
        self.assertEqual((result["total"], result["ears"], result["non_ears"]), (3, 2, 1))
        self.assertTrue(result["valid"])
        strict = ears.check_state(self.STATE, strict=True)
        self.assertFalse(strict["valid"])
        self.assertEqual([f["valid"] for f in strict["features"]], [False, True, True])

    def test_single_feature_and_unknown(self):
        result = ears.check_state(self.STATE, feature_id="b", strict=True)
        self.assertEqual(len(result["features"]), 1)
        self.assertTrue(result["valid"])
        self.assertEqual(result["features"][0]["items"][0]["pattern"], "unwanted")
        with self.assertRaises(ValueError):
            ears.check_state(self.STATE, feature_id="zzz")

    def test_resolve_state_path(self):
        tmp = tempfile.mkdtemp()
        try:
            self.assertEqual(ears.resolve_state_path(tmp), os.path.join(tmp, ".spec-master", "state.json"))
            path = os.path.join(tmp, "custom.json")
            self.assertEqual(ears.resolve_state_path(path), path)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
