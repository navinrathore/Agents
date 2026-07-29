# SOP: Default Data Analysis Workflow

This is the default operating procedure for handling general dataset exploration and tabular queries.

## Guidelines:
1. **Initial Inspection**: Always load the dataset first and print column names, row/column shapes, data types, and a small head sample.
2. **Tabular Operations**: Use standard pandas/polars code. Show intermediate steps and print results clearly to STDOUT.
3. **Execution Feedback**: If code fails, analyze the stack trace, formulate a hypothesis, and correct the code.
4. **Synthesis**: Present the final findings concisely, avoiding speculative claims not backed by execution output.
