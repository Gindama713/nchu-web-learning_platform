"""C02a pure model tests. These do not prove knowledge or paper integration."""

from copy import deepcopy
from unittest import TestCase

from backend.models.question import validate_question
from backend.shared.api import ApiError


def question(kind='single', **updates):
    value = {'type': kind, 'stem': 'PC的作用？', 'difficulty': 'easy', 'knowledge_ids': [1],
             'options': [{'key': 'A', 'text': '下一条指令地址'}, {'key': 'B', 'text': '当前数据'}], 'answer': 'A'}
    if kind not in {'single', 'multiple'}:
        value['options'] = []
    value['answer'] = {'single': 'A', 'multiple': ['A'], 'boolean': True, 'numeric': 8, 'short': '指令地址'}[kind]
    value.update(updates)
    return value


class QuestionValidationTest(TestCase):
    def rejected(self, value, previous=None):
        with self.assertRaises(ApiError) as error:
            validate_question(value, previous)
        self.assertEqual(error.exception.status, 400)

    def test_five_types_and_partial_patch_use_strict_defaults(self):
        for kind in ('single', 'multiple', 'boolean', 'numeric', 'short'):
            with self.subTest(kind=kind):
                value = validate_question(question(kind, knowledge_ids=[2, 1], explanation='说明'))
                self.assertEqual(value['knowledge_ids'], [1, 2])
                self.assertFalse(value['practice_available'])
                self.assertEqual(value['tolerance'], 0)
                updated = validate_question({'difficulty': 'hard'}, value)
                self.assertEqual(updated['answer'], value['answer'])
                self.assertEqual(value['difficulty'], 'easy')
                self.assertEqual(updated['difficulty'], 'hard')

    def test_choice_options_and_answers_reject_ambiguous_values(self):
        for changes in ({'options': []}, {'options': [{}]}, {'options': 'A'},
                        {'options': [{'key': 'A', 'text': 'one'}, {'key': 'A', 'text': 'two'}]},
                        {'options': [{'key': 'A', 'text': 'one', 'unknown': 1}, {'key': 'B', 'text': 'two'}]},
                        {'answer': True}, {'answer': 'C'}, {'answer': ['A']}):
            with self.subTest(changes=changes):
                self.rejected(question(**changes))
        for answer in ([], ['A', 'A'], ['C'], [True], 'A', None):
            self.rejected(question('multiple', answer=answer))
        options = [{'key': str(index), 'text': '选项'} for index in range(9)]
        self.rejected(question(options=options, answer='0'))

    def test_boolean_numeric_and_short_answer_boundaries(self):
        for answer in (0, 1, 'true', None, [], {}):
            self.rejected(question('boolean', answer=answer))
        for answer in (True, '8', float('nan'), float('inf'), float('-inf'), 10**1000, None):
            self.rejected(question('numeric', answer=answer))
        for tolerance in (True, '0', -1, float('nan'), float('inf')):
            self.rejected(question('numeric', tolerance=tolerance))
        self.assertEqual(validate_question(question('numeric', answer=-1.25, tolerance=0.1))['answer'], -1.25)
        self.rejected(question('boolean', tolerance=0.1))
        self.rejected(question('boolean', options=[{'key': 'A', 'text': 'x'}]))
        for answer in (' ', 1, None, 'x'*5001):
            self.rejected(question('short', answer=answer))
        self.assertEqual(validate_question(question('short', answer=' 答案 '))['answer'], '答案')
        self.rejected(question('short', practice_available=True))

    def test_ids_unknown_fields_and_empty_patches_are_rejected(self):
        for ids in ([], [1, 1], [True], [0], [-1], ['1'], [2**63], None):
            self.rejected(question(knowledge_ids=ids))
        for changes in ({'practice_available': 1}, {'type': []}, {'difficulty': []},
                        {'stem': ' '}, {'explanation': 'x'*5001}, {'unexpected': 1}):
            self.rejected(question(**changes))
        missing = deepcopy(question())
        del missing['knowledge_ids']
        self.rejected(missing)
        self.rejected({})
        self.rejected({}, validate_question(question()))
        self.rejected({'type': 'boolean'}, validate_question(question()))
