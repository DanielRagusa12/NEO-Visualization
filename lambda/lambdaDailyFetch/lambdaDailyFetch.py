import os
import boto3
import json
from datetime import datetime, timezone, date, timedelta
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
from decimal import Decimal, ROUND_HALF_UP

NASA_API_KEY = os.getenv('NASA_API_KEY')
RAW_DATA_BUCKET_NAME = os.getenv('RAW_DATA_BUCKET_NAME', 'neopipeline-raw-data')
WEBSITE_BUCKET_NAME = os.getenv('WEBSITE_BUCKET_NAME')
PUBLIC_DATA_KEY = os.getenv('PUBLIC_DATA_KEY', 'data/latest.json')
DYNAMODB_TABLE_NAME = os.getenv('DYNAMODB_TABLE_NAME', 'NEODailyData')
FEED_WINDOW_DAYS = int(os.getenv('FEED_WINDOW_DAYS', '7'))
MAX_RETURNED_NEOS = int(os.getenv('MAX_RETURNED_NEOS', '50'))

REFERENCE_OBJECTS = [
    {
        'id': 'average_human',
        'name': 'Average human',
        'height_m': Decimal('1.7'),
        'category': 'person'
    },
    {
        'id': 'statue_of_liberty',
        'name': 'Statue of Liberty',
        'height_m': Decimal('93'),
        'category': 'landmark'
    },
    {
        'id': 'eiffel_tower',
        'name': 'Eiffel Tower',
        'height_m': Decimal('330'),
        'category': 'landmark'
    },
    {
        'id': 'burj_khalifa',
        'name': 'Burj Khalifa',
        'height_m': Decimal('828'),
        'category': 'landmark'
    },
    {
        'id': 'mount_everest',
        'name': 'Mount Everest',
        'height_m': Decimal('8849'),
        'category': 'mountain'
    }
]

def clear_bucket(bucket_name, s3):
    bucket = s3.Bucket(bucket_name)
    objects_to_delete = [{'Key': obj.key} for obj in bucket.objects.all()]
    if objects_to_delete:
        bucket.delete_objects(Delete={'Objects': objects_to_delete})
        print(f"Cleared all objects from S3 bucket {bucket_name}.")
    else:
        print(f"S3 bucket {bucket_name} is already empty.")

def upload_to_s3(data, bucket_name, s3):
    filename = f"NEO-Data{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.json"
    data_json = json.dumps(data, default=str)
    s3.Object(bucket_name, filename).put(Body=data_json)
    print(f"Uploaded {filename} to S3 bucket {bucket_name}.")
    return filename

def public_fields(record, names):
    """Copy only named scalar fields, never unexpected nested data."""
    result = {}
    for name in names:
        if name not in record:
            continue
        value = record[name]
        if value is not None and not isinstance(value, (str, int, float, bool, Decimal)):
            raise ValueError(f'Unexpected structured value in public field: {name}')
        result[name] = value
    return result


def build_public_payload(data):
    """Project the private history record onto the static site's public schema."""
    public = public_fields(data, ('window_start_date', 'window_end_date', 'fetched_at'))
    public['summary'] = public_fields(data.get('summary', {}), (
        'candidate_count', 'returned_count', 'largest_neo_name', 'closest_neo_name'
    ))
    public['reference_objects'] = [
        public_fields(reference, ('id', 'name', 'height_m', 'category'))
        for reference in data.get('reference_objects', [])
    ]
    public['sort_options'] = [
        public_fields(option, ('id', 'label', 'field', 'direction'))
        for option in data.get('sort_options', [])
    ]
    sections = {
        'metrics': ('diameter_min_m', 'diameter_max_m', 'diameter_avg_m',
                    'miss_distance_km', 'miss_distance_lunar', 'velocity_kph',
                    'days_until_close_approach', 'is_hazardous'),
        'ranking': ('size_rank', 'closest_rank', 'fastest_rank',
                    'soonest_rank', 'visual_interest_rank'),
        'close_approach': ('date', 'days_until'),
        'visualization': ('diameter_avg_m', 'closest_reference_id',
                          'closest_reference_name', 'primary_reference_id',
                          'primary_reference_name', 'primary_reference_ratio',
                          'asteroid_shape_seed')
    }
    public['neos'] = []
    for neo in data.get('neos', []):
        item = public_fields(neo, ('neo_id', 'name', 'nasa_jpl_url'))
        for section, names in sections.items():
            item[section] = public_fields(neo.get(section, {}), names)
        item['visualization']['comparison_ratios'] = [
            public_fields(comparison, ('reference_id', 'reference_height_m',
                                       'neo_to_reference_ratio'))
            for comparison in neo.get('visualization', {}).get('comparison_ratios', [])
        ]
        public['neos'].append(item)
    return public


def publish_latest_data(data, bucket_name, object_key, s3):
    if not bucket_name:
        raise ValueError('WEBSITE_BUCKET_NAME is required')

    data_json = json.dumps(build_public_payload(data), default=str, separators=(',', ':'))
    s3.Object(bucket_name, object_key).put(
        Body=data_json,
        ContentType='application/json; charset=utf-8',
        CacheControl='public,max-age=300'
    )
    print(f"Published latest frontend data to s3://{bucket_name}/{object_key}.")

def fetch_nasa_data():
    start_date = date.today()
    end_date = start_date + timedelta(days=FEED_WINDOW_DAYS)
    url = f'https://api.nasa.gov/neo/rest/v1/feed?start_date={start_date.strftime("%Y-%m-%d")}&end_date={end_date.strftime("%Y-%m-%d")}&api_key={NASA_API_KEY}'

    try:
        with urlopen(url, timeout=20) as response:
            return json.loads(response.read().decode('utf-8'))
    except HTTPError as http_err:
        print(f"HTTP error occurred: {http_err}")
    except URLError as err:
        print(f"URL error occurred: {err}")
    except Exception as err:
        print(f"An error occurred: {err}")
    return None

def format_decimal(value):
    return Decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

def format_number(num, precision=2):
    return Decimal(str(round(float(num), precision)))

def decimal_from_path(data, *keys, precision=2):
    value = data
    for key in keys:
        value = value[key]
    return format_number(value, precision)

def decimal_ratio(value, divisor, precision=2):
    quantizer = Decimal('1').scaleb(-precision)
    return (value / divisor).quantize(quantizer, rounding=ROUND_HALF_UP)

def asteroid_size_class(diameter_avg_m):
    if diameter_avg_m < Decimal('25'):
        return 'tiny'
    if diameter_avg_m < Decimal('100'):
        return 'small'
    if diameter_avg_m < Decimal('300'):
        return 'medium'
    if diameter_avg_m < Decimal('1000'):
        return 'large'
    return 'huge'

def serialize_reference_objects():
    return [
        {
            'id': reference['id'],
            'name': reference['name'],
            'height_m': reference['height_m'],
            'category': reference['category']
        }
        for reference in REFERENCE_OBJECTS
    ]

def build_visualization_data(neo_data):
    diameter_min_m = format_number(neo_data['estimated_diameter']['meters']['estimated_diameter_min'], 2)
    diameter_max_m = format_number(neo_data['estimated_diameter']['meters']['estimated_diameter_max'], 2)
    diameter_avg_m = ((diameter_min_m + diameter_max_m) / Decimal('2')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    radius_avg_m = (diameter_avg_m / Decimal('2')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    comparisons = []
    for reference in REFERENCE_OBJECTS:
        comparisons.append({
            'reference_id': reference['id'],
            'reference_name': reference['name'],
            'reference_height_m': reference['height_m'],
            'neo_to_reference_ratio': decimal_ratio(diameter_avg_m, reference['height_m']),
            'reference_to_neo_ratio': decimal_ratio(reference['height_m'], diameter_avg_m)
        })

    closest_reference = min(
        comparisons,
        key=lambda comparison: abs(Decimal('1') - comparison['neo_to_reference_ratio'])
    )

    return {
        'diameter_min_m': diameter_min_m,
        'diameter_max_m': diameter_max_m,
        'diameter_avg_m': diameter_avg_m,
        'radius_avg_m': radius_avg_m,
        'primary_reference_id': 'statue_of_liberty',
        'primary_reference_name': 'Statue of Liberty',
        'primary_reference_height_m': Decimal('93'),
        'primary_reference_ratio': decimal_ratio(diameter_avg_m, Decimal('93')),
        'closest_reference_id': closest_reference['reference_id'],
        'closest_reference_name': closest_reference['reference_name'],
        'comparison_ratios': comparisons,
        'comparison_label': f"About {decimal_ratio(diameter_avg_m, Decimal('93'), 1)}x the height of the Statue of Liberty",
        'asteroid_shape_seed': neo_data['id'],
        'asteroid_size_class': asteroid_size_class(diameter_avg_m),
        'scale_hint': 'similar_to_reference' if Decimal('0.75') <= decimal_ratio(diameter_avg_m, Decimal('93')) <= Decimal('1.5') else 'larger_than_reference' if diameter_avg_m > Decimal('93') else 'smaller_than_reference',
        'render_shape': 'irregular_blob'
    }

def clean_large_numbers(neo_data):
    # Clean up absolute magnitude
    neo_data['absolute_magnitude_h'] = format_number(neo_data['absolute_magnitude_h'], 2)

    # Clean up estimated diameters with 2 decimal places
    for unit in ['kilometers', 'meters', 'miles', 'feet']:
        neo_data['estimated_diameter'][unit]['estimated_diameter_min'] = format_number(neo_data['estimated_diameter'][unit]['estimated_diameter_min'], 2)
        neo_data['estimated_diameter'][unit]['estimated_diameter_max'] = format_number(neo_data['estimated_diameter'][unit]['estimated_diameter_max'], 2)

    # Clean up close approach data with specific precision
    for approach_data in neo_data['close_approach_data']:
        approach_data['relative_velocity']['kilometers_per_second'] = format_number(approach_data['relative_velocity']['kilometers_per_second'], 5)
        approach_data['relative_velocity']['kilometers_per_hour'] = format_number(approach_data['relative_velocity']['kilometers_per_hour'], 2)
        approach_data['relative_velocity']['miles_per_hour'] = format_number(approach_data['relative_velocity']['miles_per_hour'], 2)
        approach_data['miss_distance']['astronomical'] = format_number(approach_data['miss_distance']['astronomical'], 8)
        approach_data['miss_distance']['lunar'] = format_number(approach_data['miss_distance']['lunar'], 2)
        approach_data['miss_distance']['kilometers'] = format_number(approach_data['miss_distance']['kilometers'], 2)
        approach_data['miss_distance']['miles'] = format_number(approach_data['miss_distance']['miles'], 2)

    return neo_data

def build_metrics(neo_data, approach_data):
    diameter_min_m = decimal_from_path(neo_data, 'estimated_diameter', 'meters', 'estimated_diameter_min')
    diameter_max_m = decimal_from_path(neo_data, 'estimated_diameter', 'meters', 'estimated_diameter_max')
    diameter_avg_m = ((diameter_min_m + diameter_max_m) / Decimal('2')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    close_approach_date = datetime.strptime(approach_data['close_approach_date'], '%Y-%m-%d').date()

    return {
        'diameter_min_m': diameter_min_m,
        'diameter_max_m': diameter_max_m,
        'diameter_avg_m': diameter_avg_m,
        'radius_avg_m': (diameter_avg_m / Decimal('2')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
        'miss_distance_km': decimal_from_path(approach_data, 'miss_distance', 'kilometers'),
        'miss_distance_lunar': decimal_from_path(approach_data, 'miss_distance', 'lunar'),
        'velocity_kph': decimal_from_path(approach_data, 'relative_velocity', 'kilometers_per_hour'),
        'velocity_kps': decimal_from_path(approach_data, 'relative_velocity', 'kilometers_per_second', precision=5),
        'days_until_close_approach': (close_approach_date - date.today()).days,
        'is_hazardous': neo_data['is_potentially_hazardous_asteroid']
    }

def convert_neo_data_types(neo_data, approach_data):
    neo_data = clean_large_numbers(neo_data)
    metrics = build_metrics(neo_data, approach_data)
    return {
        'neo_id': neo_data['id'],
        'name': neo_data['name'],
        'nasa_jpl_url': neo_data['nasa_jpl_url'],
        'absolute_magnitude_h': neo_data['absolute_magnitude_h'],
        'estimated_diameter': neo_data['estimated_diameter'],
        'metrics': metrics,
        'visualization': build_visualization_data(neo_data),
        'is_potentially_hazardous_asteroid': neo_data['is_potentially_hazardous_asteroid'],
        'close_approach': {
            'date': approach_data['close_approach_date'],
            'date_full': approach_data.get('close_approach_date_full'),
            'epoch_date_close_approach': approach_data.get('epoch_date_close_approach'),
            'days_until': metrics['days_until_close_approach'],
            'miss_distance_km': metrics['miss_distance_km'],
            'miss_distance_lunar': metrics['miss_distance_lunar'],
            'velocity_kph': metrics['velocity_kph'],
            'velocity_kps': metrics['velocity_kps'],
            'orbiting_body': approach_data.get('orbiting_body')
        },
        'close_approach_data': neo_data['close_approach_data']
    }

def visual_interest_score(neo):
    metrics = neo['metrics']
    diameter_score = min(metrics['diameter_avg_m'] / Decimal('10'), Decimal('40'))
    proximity_score = min(Decimal('30'), Decimal('10000000') / max(metrics['miss_distance_km'], Decimal('1')) * Decimal('30'))
    velocity_score = min(metrics['velocity_kph'] / Decimal('5000'), Decimal('20'))
    hazardous_bonus = Decimal('10') if metrics['is_hazardous'] else Decimal('0')
    soon_bonus = max(Decimal('0'), Decimal('7') - Decimal(metrics['days_until_close_approach']))
    return (diameter_score + proximity_score + velocity_score + hazardous_bonus + soon_bonus).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

def apply_rankings(processed_neos):
    ranking_configs = [
        ('size_rank', lambda neo: neo['metrics']['diameter_avg_m'], True),
        ('closest_rank', lambda neo: neo['metrics']['miss_distance_km'], False),
        ('fastest_rank', lambda neo: neo['metrics']['velocity_kph'], True),
        ('soonest_rank', lambda neo: neo['metrics']['days_until_close_approach'], False),
        ('visual_interest_rank', lambda neo: neo['ranking']['visual_interest_score'], True)
    ]

    for neo in processed_neos:
        neo['ranking'] = {
            'visual_interest_score': visual_interest_score(neo)
        }

    for rank_name, key_func, reverse in ranking_configs:
        sorted_neos = sorted(processed_neos, key=key_func, reverse=reverse)
        for index, neo in enumerate(sorted_neos, start=1):
            neo['ranking'][rank_name] = index

    return processed_neos

def flatten_neo_feed(res_json):
    processed_neos = []
    for approach_date in sorted(res_json['near_earth_objects'].keys()):
        for neo_data in res_json['near_earth_objects'][approach_date]:
            approach_data = next(
                (
                    approach
                    for approach in neo_data['close_approach_data']
                    if approach['close_approach_date'] == approach_date
                ),
                neo_data['close_approach_data'][0]
            )
            processed_neos.append(convert_neo_data_types(neo_data, approach_data))
    return apply_rankings(processed_neos)

def sort_options():
    return [
        {'id': 'visual_interest', 'label': 'Most Interesting', 'field': 'ranking.visual_interest_rank', 'direction': 'asc'},
        {'id': 'largest', 'label': 'Largest Size', 'field': 'metrics.diameter_avg_m', 'direction': 'desc'},
        {'id': 'closest', 'label': 'Closest Pass', 'field': 'metrics.miss_distance_km', 'direction': 'asc'},
        {'id': 'fastest', 'label': 'Fastest Speed', 'field': 'metrics.velocity_kph', 'direction': 'desc'},
        {'id': 'soonest', 'label': 'Soonest Approach', 'field': 'metrics.days_until_close_approach', 'direction': 'asc'},
        {'id': 'hazardous', 'label': 'Potentially Hazardous', 'field': 'metrics.is_hazardous', 'direction': 'desc'}
    ]

def build_daily_summary(all_neos, returned_neos):
    if not all_neos:
        return {
            'candidate_count': 0,
            'returned_count': 0,
            'hazardous_count': 0
        }

    largest_neo = min(all_neos, key=lambda neo: neo['ranking']['size_rank'])
    closest_neo = min(all_neos, key=lambda neo: neo['ranking']['closest_rank'])
    fastest_neo = min(all_neos, key=lambda neo: neo['ranking']['fastest_rank'])
    hazardous_count = sum(1 for neo in all_neos if neo['is_potentially_hazardous_asteroid'])

    return {
        'candidate_count': len(all_neos),
        'returned_count': len(returned_neos),
        'neo_count': len(returned_neos),
        'hazardous_count': hazardous_count,
        'largest_neo_id': largest_neo['neo_id'],
        'largest_neo_name': largest_neo['name'],
        'largest_neo_diameter_avg_m': largest_neo['metrics']['diameter_avg_m'],
        'closest_neo_id': closest_neo['neo_id'],
        'closest_neo_name': closest_neo['name'],
        'closest_neo_miss_distance_km': closest_neo['metrics']['miss_distance_km'],
        'fastest_neo_id': fastest_neo['neo_id'],
        'fastest_neo_name': fastest_neo['name'],
        'fastest_neo_velocity_kph': fastest_neo['metrics']['velocity_kph']
    }

def lambda_handler(event, context):
    # Initialize AWS resources
    s3 = boto3.resource('s3')
    dynamodb = boto3.resource('dynamodb')

    # Fetch NASA data
    resJson = fetch_nasa_data()
    if not resJson:
        print("No data fetched from NASA.")
        return {"statusCode": 500, "body": json.dumps("Failed to fetch data from NASA.")}

    # Clear S3 bucket
    bucket_name = RAW_DATA_BUCKET_NAME
    # clear_bucket(bucket_name, s3)

    # Upload data to S3
    raw_s3_key = upload_to_s3(resJson, bucket_name, s3)

    # Aggregate NEO data for the configured feed window
    fetch_date = date.today().strftime("%Y-%m-%d")
    window_end_date = (date.today() + timedelta(days=FEED_WINDOW_DAYS)).strftime("%Y-%m-%d")

     # Calculate expiry date
    expiry_date = int((datetime.now(timezone.utc) + timedelta(days=30)).timestamp())
    print(f"Expiry Date (timestamp): {expiry_date}")
    print(f"Expiry Date (readable): {datetime.fromtimestamp(expiry_date, timezone.utc)}")

    all_neos = flatten_neo_feed(resJson)
    returned_neos = sorted(all_neos, key=lambda neo: neo['ranking']['visual_interest_rank'])[:MAX_RETURNED_NEOS]

    # Insert aggregated data into DynamoDB
    aggregated_data = {
        'fetch_date': fetch_date,
        'window_start_date': fetch_date,
        'window_end_date': window_end_date,
        'feed_window_days': FEED_WINDOW_DAYS,
        'max_returned_neos': MAX_RETURNED_NEOS,
        'fetched_at': datetime.now(timezone.utc).isoformat(),
        'raw_s3_bucket': bucket_name,
        'raw_s3_key': raw_s3_key,
        'reference_objects': serialize_reference_objects(),
        'sort_options': sort_options(),
        'summary': build_daily_summary(all_neos, returned_neos),
        'neos': returned_neos,
        'expiryDate': expiry_date  # Set TTL 30 days from now
    }

    # Insert aggregated data into DynamoDB
    table = dynamodb.Table(DYNAMODB_TABLE_NAME)
    table.put_item(Item=aggregated_data)
    print(f"Inserted NEO data for date {fetch_date}")

    # Publish only after the processed history write succeeds. S3 PutObject is
    # atomic, so a failed run leaves the previous successful dataset available.
    publish_latest_data(aggregated_data, WEBSITE_BUCKET_NAME, PUBLIC_DATA_KEY, s3)

    return {"statusCode": 200, "body": json.dumps("Success")}
