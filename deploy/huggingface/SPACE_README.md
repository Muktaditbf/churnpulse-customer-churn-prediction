---
title: ChurnPulse — Customer Churn Prediction
emoji: 📉
colorFrom: green
colorTo: blue
sdk: docker
app_port: 7860
startup_duration_timeout: 30m
license: mit
short_description: Real-time customer churn prediction with Kafka + Flink
---

# ChurnPulse — Real-Time Customer Churn Prediction

Predict which customers are about to leave, see why, and get the action that keeps them — live.

This Space runs the **complete real-time platform** in one container: Apache Kafka, Apache Flink (PyFlink),
PostgreSQL, a FastAPI service, an event simulator and the React dashboard.

- **Profile model** (LightGBM): 85.5% accuracy · ROC-AUC 0.917
- **Survey model** (LightGBM): 96.5% accuracy · ROC-AUC 0.993
- Add customers, import CSVs, see SHAP explanations and ranked retention actions

Waking up takes about 2 minutes while Flink scores all 7,043 customers. This is a public demo: data resets when
the Space restarts.

Source code, documentation and results: **https://github.com/Muktaditbf/churnpulse-customer-churn-prediction**

Developed by **Muktadi**.
