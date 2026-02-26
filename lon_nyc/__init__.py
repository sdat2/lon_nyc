"""lon_nyc: download and analyse NYC hourly rain data from NOAA ISD.

Typical usage::

    from lon_nyc import noaa, analysis, config

    s3 = noaa.make_s3_client()
    keys = noaa.generate_s3_file_keys(config.NYC_STATION_ID, 2023, 2023)
    raw = noaa.download_and_concatenate_s3_csvs(s3, noaa.S3_BUCKET, keys)
    processed = noaa.process_precipitation_data(raw)
    print(analysis.rainy_hours_summary(processed))
"""

from lon_nyc import analysis, config, noaa

__all__ = ["analysis", "config", "noaa"]
