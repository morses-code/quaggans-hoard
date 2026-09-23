import unittest
import wiki_notes


class WikiNoteTests(unittest.TestCase):
    def page(self, notes, item_id=1, before='', after=''):
        return {'parse': {'title': 'Example', 'revid': 123, 'text': {'*':
            f'<div class="infobox item"><span data-type="item" data-id="{item_id}"></span></div>'
            + before + '<h2><span>Notes</span><span>[edit]</span></h2><ul>'
            + ''.join('<li>' + note + '</li>' for note in notes)
            + '</ul><h2>Other section</h2>' + after}}}

    def test_complete_unqualified_statement(self):
        r = wiki_notes.parse_page(1, self.page(['This item can be safely destroyed after acquisition.']))
        self.assertEqual(r['state'], 'explicit')
        self.assertEqual(r['revision'], 123)

    def test_reading_tradeoff_matches_notes_regardless_of_item_id(self):
        note = 'Other than to access collected pages before acquiring the completed journal, this item can be safely destroyed.'
        for item_id in [79166, 79299, 12345]:
            result = wiki_notes.parse_page(item_id, self.page([note], item_id=item_id))
            self.assertEqual(result['state'], 'explicit')
            self.assertIn('collected pages', result['reviewed_caveat'])

    def test_reading_tradeoff_does_not_ignore_changed_context(self):
        note = 'Other than to access collected pages before acquiring the completed journal, this item can be safely destroyed.'
        for notes in [[note + ' Keep it for crafting.'], [note, 'Required for another collection.'],
                      [note.replace('can be', 'cannot be')],
                      [note.replace('access collected pages', 'complete the achievement')]]:
            self.assertEqual(wiki_notes.parse_page(1, self.page(notes))['state'], 'review')

    def test_reading_tradeoff_handles_formatting_and_case(self):
        note = 'OTHER THAN to <b>access collected pages</b> before acquiring the completed journal, this item can be safely destroyed.'
        self.assertEqual(wiki_notes.parse_page(1, self.page([note]))['state'], 'explicit')

    def test_conditional_negative_and_conflicting_notes_not_approved(self):
        for notes in [
            ['This item can be safely destroyed after completing the achievement.'],
            ['This item cannot be safely destroyed.'],
            ['Do not destroy this item.'],
            ['This item can be safely destroyed.', 'Keep one for a later recipe.'],
            ['This item can be safely destroyed. However, it is useful for crafting.'],
            ['The container can be safely destroyed.'],
        ]:
            self.assertEqual(wiki_notes.parse_page(1, self.page(notes))['state'], 'review')

    def test_page_identity_must_match(self):
        r = wiki_notes.parse_page(1, self.page(['This item can be safely destroyed.'], item_id=2))
        self.assertEqual(r['state'], 'unverified')
        self.assertEqual(r['notes'], [])

    def test_only_notes_are_extracted_and_markup_stays_text(self):
        r = wiki_notes.parse_page(1, self.page(['Keep <b>this item</b> &amp; review its uses.'],
            before='<p>This item can be safely destroyed.</p>', after='<p>Another item can be safely destroyed.</p>'))
        self.assertEqual(r['notes'], ['Keep this item & review its uses.'])
        self.assertEqual(r['state'], 'review')

    def test_no_notes_is_not_disposal_approval(self):
        r = wiki_notes.parse_page(1, self.page([]))
        self.assertEqual(r['state'], 'none')

    def test_ambiguous_item_ids_are_rejected(self):
        page = self.page(['This item can be safely destroyed.'])
        page['parse']['text']['*'] += '<div class="infobox item"><span data-type="item" data-id="2"></span></div>'
        self.assertEqual(wiki_notes.parse_page(1, page)['state'], 'unverified')
