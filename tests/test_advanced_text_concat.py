import pathlib
import sys
import unittest


sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from advanced_text_concat import AdvancedTextConcat, MAX_TEXT_INPUTS


class AdvancedTextConcatTests(unittest.TestCase):
    def test_widget_order_keeps_all_text_rows_before_settings(self):
        schema = AdvancedTextConcat.INPUT_TYPES()
        names = [
            *schema["optional"],
        ]

        self.assertEqual(
            names[:5],
            [
                "text1",
                "text2",
                "text3",
                "text4",
                "text5",
            ],
        )
        self.assertIn(f"text{MAX_TEXT_INPUTS}", schema["optional"])
        self.assertEqual(names[-2:], ["delimiter", "decode_escapes"])
        self.assertEqual(len(names), MAX_TEXT_INPUTS + 2)

    def test_empty_rows_are_skipped(self):
        result = AdvancedTextConcat().concat(
            text1="first",
            text2="",
            text3="third",
            delimiter="|",
            text4="",
            text5="",
        )

        self.assertEqual(result, ("first|third",))

    def test_dynamic_rows_are_concatenated_in_order(self):
        result = AdvancedTextConcat().concat(
            text1="one",
            text2="two",
            text3="",
            delimiter=", ",
            text4="",
            text5="",
            text8="eight",
            text6="six",
        )

        self.assertEqual(result, ("one, two, six, eight",))

    def test_decode_escapes_applies_to_rows_and_delimiter(self):
        result = AdvancedTextConcat().concat(
            text1=r"line 1\nline 2",
            text2=r"tab\ttext",
            text3="",
            delimiter=r"\n",
            text4="",
            text5="",
            decode_escapes=True,
        )

        self.assertEqual(
            result,
            ("line 1\nline 2\ntab\ttext",),
        )

    def test_removed_cleanup_options_are_ignored(self):
        result = AdvancedTextConcat().concat(
            text1="  keep spaces  ",
            text2="keep spaces",
            text3="",
            delimiter="|",
            text4="",
            text5="",
            deduplicate=True,
            trim_parts=True,
        )

        self.assertEqual(
            result,
            ("  keep spaces  |keep spaces",),
        )


if __name__ == "__main__":
    unittest.main()
