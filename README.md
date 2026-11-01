# NEO Visualization

[![Animated preview of the live NEO Visualization site](docs/images/live-site.gif)](https://d1wsbj4s2jjqv0.cloudfront.net)

NEO Visualization is an AWS data pipeline and static frontend for exploring near-Earth object close approaches. It fetches NASA NeoWs data every day, stores the raw response, writes processed history to DynamoDB, and publishes a curated dataset for the frontend through Amazon S3 and CloudFront.

The frontend visualizes each near-Earth object against familiar vertical references: an average human, the Statue of Liberty, the Eiffel Tower, the Burj Khalifa, and Mount Everest.

Live site: [https://d1wsbj4s2jjqv0.cloudfront.net](https://d1wsbj4s2jjqv0.cloudfront.net)

## Architecture

```text
Browser
   |
   v
CloudFront + AWS WAF
   |
   | Origin Access Control
   v
Private S3 Website Bucket
   |-- Static HTML, CSS, JavaScript, and assets
   `-- data/latest.json

EventBridge Daily Schedule
   |
   v
Lambda: neo-pipeline-daily-fetch
   |-- NASA NeoWs API
   |-- Private S3 raw data bucket
   |-- DynamoDB: NEODailyData
   `-- Private S3 website bucket: data/latest.json
```

## How It Works

The project has two main paths: scheduled ingestion and static content delivery.

## Scheduled Ingestion

EventBridge runs the daily fetch Lambda on a schedule. The Lambda requests a seven-day near-Earth object feed from NASA NeoWs, starting from the current date.

After fetching the NASA response, the Lambda stores the raw payload in a private S3 bucket. This preserves the original response separately from the processed application data.

The Lambda normalizes the feed into a frontend-friendly record. It calculates average diameter, close-approach distance, velocity, days until approach, hazard status, and comparison ratios against supported reference objects. It also ranks objects by size, closest pass, fastest speed, soonest approach, hazard status, and overall visual interest.

The processed daily record is written to DynamoDB using `fetch_date` as the partition key. DynamoDB TTL is enabled through the `expiryDate` field, and raw S3 objects expire after 30 days.

After processing succeeds, the Lambda publishes the current frontend dataset to `data/latest.json` in the private website bucket. The last successful public dataset remains available if a later ingestion run fails.

## Static Delivery

CloudFront serves the website and `data/latest.json` from the private website S3 bucket. Origin Access Control restricts bucket reads to the CloudFront distribution, and S3 Block Public Access remains enabled.

The distribution uses the AWS-managed `CachingOptimized` cache policy and the CloudFront Free flat-rate plan with AWS WAF. Static assets are cached for 24 hours, while the site documents and current dataset use a five-minute cache duration.

Browser requests do not invoke Lambda or query DynamoDB. The frontend retrieves the current dataset from the same CloudFront origin:

```text
GET /data/latest.json
```

## Frontend

The frontend is a static site in `neowebsite/static/`. It renders the current NEO window, summary statistics, sortable observation cards, and per-card reference selectors.

The visualization is built with HTML, CSS, SVG, and JavaScript. Each asteroid card uses seeded CSS variation so objects have different shapes, crater positions, sizes, and animation timing while remaining lightweight to render.

The published dataset includes the available sort options and reference-object metadata used to render the controls and compare each NEO against supported vertical references.

## Infrastructure

Terraform manages the AWS infrastructure in `terraform/`.

Managed resources include:

- CloudFront distribution for the public website and current dataset
- CloudFront Origin Access Control for private S3 access
- Private, versioned S3 website bucket containing static files and `data/latest.json`
- Private S3 bucket for raw NASA responses with a 30-day lifecycle
- Lambda function for daily ingestion: `neo-pipeline-daily-fetch`
- DynamoDB table for processed history: `NEODailyData`
- EventBridge daily schedule
- CloudWatch log groups with bounded retention
- IAM roles and policies for Lambda, DynamoDB, S3, EventBridge, and CloudFront access