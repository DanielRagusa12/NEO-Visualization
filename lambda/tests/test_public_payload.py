"""Public-data boundary tests. No AWS SDK, credentials, or network are used."""
import contextlib
import copy
from decimal import Decimal
import importlib.util
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    'daily_fetch_under_test', ROOT / 'lambda/lambdaDailyFetch/lambdaDailyFetch.py')
fetcher = importlib.util.module_from_spec(spec)
stub = SimpleNamespace(resource=mock.Mock(side_effect=AssertionError('AWS access is forbidden')))
with mock.patch.dict(sys.modules, {'boto3': stub}), mock.patch('os.getenv', side_effect=lambda _name, default=None: default):
    spec.loader.exec_module(fetcher)


class PublicPayloadTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT / 'neowebsite/tests/fixtures/latest.json').read_text())
        self.data.update(raw_s3_bucket='synthetic-raw', raw_s3_key='synthetic-source.json',
                         expiryDate=123, private_debug='PRIVATE_TEST_SENTINEL')
        self.data['sort_options'] = fetcher.sort_options()
        self.data['summary']['private_debug'] = 'PRIVATE_TEST_SENTINEL'
        for reference in self.data['reference_objects']:
            reference['private_debug'] = 'PRIVATE_TEST_SENTINEL'
        for option in self.data['sort_options']:
            option['private_debug'] = 'PRIVATE_TEST_SENTINEL'
        for index, neo in enumerate(self.data['neos']):
            neo['private_debug'] = 'PRIVATE_TEST_SENTINEL'
            neo['close_approach_data'] = [{'private_debug': 'PRIVATE_TEST_SENTINEL'}]
            neo['metrics'].update(diameter_min_m=Decimal('10.5'), diameter_max_m=Decimal('200.5'),
                                  miss_distance_km=Decimal('1000000'), days_until_close_approach=index)
            neo['ranking']['soonest_rank'] = index + 1
            for section in ['metrics', 'ranking', 'close_approach', 'visualization']:
                neo[section]['private_debug'] = 'PRIVATE_TEST_SENTINEL'
            neo['visualization']['comparison_ratios'] = [{
                'reference_id': 'average_human', 'reference_height_m': Decimal('1.7'),
                'neo_to_reference_ratio': Decimal('5.25'), 'private_debug': 'PRIVATE_TEST_SENTINEL'
            }]
        self.events = []

    def test_allowlist_excludes_private_fields_at_every_level_and_keeps_ui_contract(self):
        before = copy.deepcopy(self.data)
        public = fetcher.build_public_payload(self.data)
        encoded = json.dumps(public, default=str)
        self.assertNotIn('PRIVATE_TEST_SENTINEL', encoded)
        for name in ['raw_s3_bucket', 'raw_s3_key', 'expiryDate', 'close_approach_data', '_fixture']:
            self.assertNotIn(name, encoded)
        self.assertEqual(set(public), {'window_start_date', 'window_end_date', 'fetched_at',
                                      'summary', 'reference_objects', 'sort_options', 'neos'})
        self.assertEqual(public['fetched_at'], self.data['fetched_at'])
        self.assertEqual(len(public['reference_objects']), 5)
        self.assertEqual(public['neos'][0]['metrics']['diameter_min_m'], Decimal('10.5'))
        for option in public['sort_options']:
            for neo in public['neos']:
                value = neo
                for part in option['field'].split('.'):
                    value = value[part]
                self.assertIsInstance(value, (int, float, bool, Decimal))
        self.assertEqual(self.data, before, 'Private history must not be mutated')

    def test_public_put_uses_filtered_body_and_preserves_decimal_serialization(self):
        s3 = mock.Mock()
        fetcher.publish_latest_data(self.data, 'synthetic-site', 'data/latest.json', s3)
        s3.Object.assert_called_once_with('synthetic-site', 'data/latest.json')
        args = s3.Object.return_value.put.call_args.kwargs
        public = json.loads(args['Body'])
        self.assertEqual(public['neos'][0]['metrics']['diameter_min_m'], '10.5')
        self.assertNotIn('PRIVATE_TEST_SENTINEL', args['Body'])
        self.assertEqual(args['ContentType'], 'application/json; charset=utf-8')
        self.assertEqual(args['CacheControl'], 'public,max-age=300')

    def test_unexpected_structured_values_fail_before_public_write(self):
        self.data['fetched_at'] = {'unexpected': 'PRIVATE_TEST_SENTINEL'}
        s3 = mock.Mock()
        with self.assertRaises(ValueError):
            fetcher.publish_latest_data(self.data, 'synthetic-site', 'data/latest.json', s3)
        s3.Object.assert_not_called()

    def invoke(self, history_failure=False, nasa_failure=False):
        def object_for(bucket, key):
            return SimpleNamespace(put=lambda **kwargs: self.events.append({
                'kind': 'raw' if bucket == 'synthetic-raw' else 'public', 'key': key, **kwargs
            }))

        def history_put(**kwargs):
            self.events.append({'kind': 'history', **kwargs})
            if history_failure:
                raise RuntimeError('Synthetic history failure')

        s3 = SimpleNamespace(Object=object_for)
        dynamodb = SimpleNamespace(Table=lambda _name: SimpleNamespace(put_item=history_put))
        with mock.patch.object(fetcher.boto3, 'resource', side_effect=lambda service: {'s3': s3, 'dynamodb': dynamodb}[service]), \
             mock.patch.object(fetcher, 'fetch_nasa_data', return_value=None if nasa_failure else {'synthetic': True}), \
             mock.patch.object(fetcher, 'flatten_neo_feed', return_value=self.data['neos']), \
             mock.patch.object(fetcher, 'build_daily_summary', return_value=self.data['summary']), \
             mock.patch.multiple(fetcher, RAW_DATA_BUCKET_NAME='synthetic-raw', WEBSITE_BUCKET_NAME='synthetic-site',
                                 DYNAMODB_TABLE_NAME='synthetic-history', PUBLIC_DATA_KEY='data/latest.json'), \
             contextlib.redirect_stdout(io.StringIO()):
            return fetcher.lambda_handler({}, None)

    def test_handler_writes_private_history_before_filtered_public_data(self):
        self.assertEqual(self.invoke()['statusCode'], 200)
        self.assertEqual([e['kind'] for e in self.events], ['raw', 'history', 'public'])
        history = self.events[1]['Item']
        self.assertEqual(history['raw_s3_bucket'], 'synthetic-raw')
        self.assertIn('raw_s3_key', history)
        body = self.events[2]['Body']
        self.assertNotIn('raw_s3_bucket', body)
        self.assertNotIn('raw_s3_key', body)
        self.assertNotIn('PRIVATE_TEST_SENTINEL', body)

    def test_failed_history_write_never_replaces_public_feed(self):
        with self.assertRaises(RuntimeError):
            self.invoke(history_failure=True)
        self.assertEqual([e['kind'] for e in self.events], ['raw', 'history'])

    def test_failed_nasa_fetch_never_replaces_public_feed(self):
        self.assertEqual(self.invoke(nasa_failure=True)['statusCode'], 500)
        self.assertEqual(self.events, [])


if __name__ == '__main__':
    unittest.main()
