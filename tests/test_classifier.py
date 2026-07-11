import unittest

from codex_intercom.classifier import classify_stop


class ClassifierTests(unittest.TestCase):
    def test_classification_cases(self):
        cases = (
            ("Qual opção você prefere?", "response_required"),
            ("Please confirm which environment I should use.", "response_required"),
            ("Preciso que você escolha uma das opções.", "response_required"),
            ("Estou bloqueado: preciso da credencial para continuar.", "blocked"),
            ("I cannot continue without access to the signing key.", "blocked"),
            ("The failing test was fixed and all checks now pass.", "complete"),
            ("O erro foi corrigido e a implementação foi verificada.", "complete"),
            ("Implementação concluída e verificada.", "complete"),
        )
        for message, expected in cases:
            with self.subTest(message=message):
                self.assertEqual(classify_stop(message), expected)

    def test_only_the_tail_is_classified(self):
        old_blocker = "I cannot continue. " + ("x" * 1400)
        self.assertEqual(classify_stop(old_blocker + " Finished and verified."), "complete")


if __name__ == "__main__":
    unittest.main()
