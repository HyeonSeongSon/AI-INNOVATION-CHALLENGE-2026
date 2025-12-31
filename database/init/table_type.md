1.persona table
영문 컬럼명 (Column Name)	데이터 타입
persona_id	varchar (PK)
name	varchar
gender	varchar
age	integer
occupation	varchar
skin_type	text[]
skin_concerns	text[]
personal_color	varchar
shade_number	integer
preferred_colors	text[]
preferred_ingredients	text[]
avoided_ingredients	text[]
preferred_scents	text[]
values	text[]
skincare_routine	varchar
main_environment	varchar
preferred_texture	text[]
pets	varchar
avg_sleep_hours	integer
stress_level	varchar
digital_device_usage_time	integer
shopping_style	varchar
purchase_decision_factors	text[]
persona_created_at timestamp

2.analysis results table
영문 컬럼명 (Column Name)	데이터 타입
analysis_id	serial (PK)
persona_id	(FK)
analysis_result	text
analysis_created_at	timestamp

3.search query table
영문 컬럼명 (Column Name)	데이터 타입
query_id	(PK)
analysis_id	(FK)
search_query	text
query_created_at	timestamp

4.Product Table
영문 컬럼명 (Column Name)	데이터 타입
product_id	varchar (PK)
vectordb_id	varchar (FK)
product_name	varchar
brand	varchar
product_tag	varchar
rating	nemunic
review_count	integer
original_price	integer
discount_rate	integer
sale_price	integer
skin_type	text[]
skin_concerns	text[]
preferred_colors	text[]
preferred_ingredients	text[]
avoided_ingredients	text[]
preferred_scents	text[]
values	text[]
exclusive_product	varchar
personal_color	text[]
skin_shades	text[integer]
product_image_url	text[]
product_page_url	text
product_created_at	timestamp