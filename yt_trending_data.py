import os
import pandas as pd
import zipfile
from datetime import datetime
import json
from snowflake.connector.pandas_tools import write_pandas
from prefect.blocks.system import Secret
from prefect import flow, task, get_run_logger
from prefect_snowflake import SnowflakeCredentials, SnowflakeConnector

@task(name="Get YouTube trending dataset from Kaggle")
def yt_trending_data_pull():
    kaggle_user = Secret.load("kaggle-username").get()
    kaggle_key = Secret.load("kaggle-key").get()
    os.environ["KAGGLE_USERNAME"] = kaggle_user
    os.environ["KAGGLE_KEY"] = kaggle_key
    
    us_yt_trending_df = pd.DataFrame()
    us_yt_category_id_df = pd.DataFrame()

    from kaggle.api.kaggle_api_extended import KaggleApi
    api = KaggleApi()
    api.authenticate()  # uses ~/.kaggle/kaggle.json or KAGGLE_USERNAME/KAGGLE_KEY

    api.dataset_download_file(
        "rsrishav/youtube-trending-video-dataset",
        "US_youtube_trending_data.csv",
        path="."
    )

    api.dataset_download_file(
        "rsrishav/youtube-trending-video-dataset",
        "US_category_id.json",
        path="."
    )

    with zipfile.ZipFile("US_youtube_trending_data.csv.zip", "r") as z:
        name = z.namelist()[0]
        with z.open(name) as f:
            us_yt_trending_df = pd.read_csv(f, encoding="utf-8")
            
    with open("US_category_id.json", "r") as f:
        us_yt_category_data = json.load(f)
        us_yt_category_id_df = pd.json_normalize(us_yt_category_data["items"])

    # Remove dots in column names
    us_yt_category_id_df.columns = us_yt_category_id_df.columns.str.replace('snippet.', '', regex=False)

    return us_yt_trending_df, us_yt_category_id_df

@task(name="Load YouTube trending dataset into Snowflake")
def yt_trending_data_load(logger, us_yt_trending_df, us_yt_category_id_df):
    snowflake_credentials = SnowflakeCredentials.load("snowflake-credentials")
    snowflake_connector = SnowflakeConnector(
        database="CLASS_PROJECT",
        warehouse="COMPUTE_WH",
        schema="YT_TRENDING_DATA",
        credentials=snowflake_credentials
    )
    with snowflake_connector.get_connection() as conn:
        success, nchunks, nrows, _ = write_pandas(conn, us_yt_trending_df, table_name="STG_US_YT_TRENDING", auto_create_table=True, overwrite=True, quote_identifiers=False)
        if success:
            logger.info(f"Wrote {nrows:,} rows to STG_US_YT_TRENDING")
        else:
            logger.error("Failed to write data to STG_US_YT_TRENDING")
        success, nchunks, nrows, _ = write_pandas(conn, us_yt_category_id_df, table_name="STG_US_YT_CATEGORY", auto_create_table=True, overwrite=True, quote_identifiers=False)
        if success:
            logger.info(f"Wrote {nrows:,} rows to STG_US_YT_CATEGORY")
        else:
            logger.error("Failed to write data to STG_US_YT_CATEGORY")

@flow(retries=1)
def yt_trending_data():
    logger = get_run_logger()
    us_yt_trending_df, us_yt_category_id_df = yt_trending_data_pull()
    if us_yt_trending_df.shape[0] > 0 and us_yt_category_id_df.shape[0] > 0:
        logger.info(f"YouTube trending dataset contains {us_yt_trending_df.shape[0]:,} rows")
        logger.info(f"Category dataset contains {us_yt_category_id_df.shape[0]:,} rows")
        us_yt_trending_df['dw_create_ts'] = datetime.now().isoformat()
        us_yt_category_id_df['dw_create_ts'] = datetime.now().isoformat()
        yt_trending_data_load(logger, us_yt_trending_df, us_yt_category_id_df)
    else:
        logger.error("Dataset contains no data! Please check the logs for more info!")

if __name__ == "__main__":
    yt_trending_data()