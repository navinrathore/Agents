# SOP: Data Cleaning & Preprocessing

Use this procedure when the query involves data cleaning, handling nulls, duplicates, outliers, filtering, or general data quality preprocessing.

## Guidelines:
1. **Detect Anomalies**:
   - Scan for null/missing values using `.isnull().sum()`.
   - Scan for duplicate records using `.duplicated().sum()`.
   - Use `.describe()` to identify anomalous min/max values indicating outliers or bad inputs.
2. **Handle Nulls & Duplicates**:
   - Explicitly drop duplicates or imputation/mode fill nulls based on context.
   - For missing numeric data, prefer median imputation over mean if distributions are skewed.
3. **Data Type Conversions**:
   - Parse dates explicitly using `pd.to_datetime()`.
   - Strip leading/trailing whitespaces from string columns.
   - Convert categorical columns to optimal numeric or category types to save memory.
4. **Validation Log**:
   - Always print the shape of the data *before* and *after* cleaning so changes are checkable.
