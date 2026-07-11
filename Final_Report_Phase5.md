# Final Report — Institutional and Financial Aid Factors Influencing Student Outcomes in U.S. Higher Education

**Independent Study in Data Mining and Python**
**Dataset:** IPEDS 2022 — Integrated Postsecondary Education Data System
**Author:** Vijetha Palaparthi
**Advisor:** Dr. Oguz

---

## 1. Introduction and Research Questions

This study applies data mining techniques to analyze how institutional characteristics and financial aid patterns relate to student outcomes at U.S. four-year colleges and universities. The analysis uses institution-level data from the 2022 Integrated Postsecondary Education Data System (IPEDS), which covers enrollment, financial aid, graduation rates, retention rates, tuition, instructional spending, and institutional characteristics for degree-granting postsecondary institutions.

The study addresses three research questions:

1. **How does financial aid impact student outcomes?** Specifically, how do grants, loans, and Pell Grant recipient percentages relate to graduation and retention rates?
2. **How do institutional factors influence student success?** This includes tuition, student-faculty ratio, instructional spending per FTE, and enrollment structure.
3. **How do outcomes differ across institution types?** This compares public versus private, urban versus rural, and selective versus open-access institutions.

The analytical pipeline spans five phases: data preprocessing and exploratory analysis (Phase 1), feature engineering (Phase 2), regression modeling and model selection (Phase 3), clustering and SHAP interpretability (Phase 4), and this final integrated report (Phase 5). Detailed code and outputs are documented in the per-phase notebooks.

---

## 2. Data and Methods

### 2.1 Dataset and Preprocessing (Phase 1)

The raw IPEDS 2022 dataset was filtered to U.S. four-year degree-granting institutions, yielding 2,716 institutions across 26 variables. Key preprocessing steps included:

- **Column renaming** from verbose IPEDS names to short aliases (e.g., `tuition`, `pell_pct`, `retention_rate`).
- **Merging GASB and FASB** instructional expenditure columns into a single `instr_exp_per_fte` variable, since public institutions report under GASB and private institutions under FASB accounting standards.
- **Missing value handling**: Numeric predictors were imputed using global medians. Admission rate (`admit_rate`) received hierarchical group-based median imputation (by `control × locale_broad`, then `control`, then overall median), with a binary `admit_rate_missing` flag to preserve the missingness signal. Target variables (graduation and retention rates) were intentionally left unimputed to avoid fabricating outcomes.
- **Pre- and post-imputation verification** confirmed that imputation preserved distributional properties: means, medians, skewness, and outlier counts remained stable.

Four target outcomes were defined: six-year graduation rate (`grad_rate_6yr`), overall graduation rate (`grad_rate_total`), Pell Grant recipient graduation rate (`pell_grad_rate`), and full-time retention rate (`retention_rate`).

### 2.2 Feature Engineering (Phase 2)

Three engineered features were created to capture relationships not expressed by raw variables alone:

| Feature | Formula | Rationale |
|---|---|---|
| `affordability_index` | `inst_grant_aid / avg_fed_loan` | Measures how much institutional grant aid offsets student borrowing. Higher values indicate greater institutional generosity relative to loan burden. |
| `parttime_share` | `parttime_enroll / total_enroll` | Captures enrollment composition. Institutions with high part-time shares may face different retention dynamics. |
| `loan_burden_ratio` | `(avg_fed_loan × loan_pct / 100) / inst_grant_aid` | Estimates aggregate borrowing exposure relative to institutional aid. Higher values indicate greater reliance on loans versus grants. |

Feature ablation testing in Phase 3 confirmed that `affordability_index` and `parttime_share` contributed meaningful predictive gains for graduation-related targets, while `loan_burden_ratio` provided smaller but consistent improvements.

### 2.3 Regression Modeling and Model Selection (Phase 3)

Forty model configurations were evaluated: five algorithms (Linear Regression, Ridge, Lasso, Random Forest, Gradient Boosting) × two feature sets (Baseline, Engineered) × four target outcomes. Each configuration was evaluated using 5-fold cross-validation on the training set, and the best model per target was selected for final held-out test evaluation.

The train-test split used an 80/20 ratio with `random_state=42`. The exact train and test indices were saved as joblib artifacts so that Phase 4 could reuse the identical holdout rows for SHAP analysis, preventing data leakage.

**Final selected models and held-out test performance:**

| Target | Algorithm | Feature Set | Train N | Test N | Test R² | Test MAE |
|---|---|---|---|---|---|---|
| `grad_rate_6yr` | Gradient Boosting | Engineered | 1,532 | 383 | 0.549 | 10.4 |
| `grad_rate_total` | Random Forest | Engineered | 1,734 | 434 | 0.494 | 10.5 |
| `pell_grad_rate` | Random Forest | Engineered | 1,457 | 365 | 0.455 | 11.1 |
| `retention_rate` | Random Forest | Baseline | 1,598 | 400 | 0.306 | 8.9 |

Ensemble methods (Random Forest and Gradient Boosting) consistently outperformed linear models across all targets. Engineered features improved performance for graduation-related targets; retention rate performed best with the baseline feature set.

Permutation importance analysis identified `pell_pct` as the strongest predictor across all targets, followed by `total_enroll`, `instr_exp_per_fte`, and `admit_rate`. Subgroup error analysis revealed systematically higher prediction errors for private for-profit institutions and institutions with fewer than 1,000 students, suggesting that these underrepresented subgroups are harder for the models to capture.

### 2.4 PCA, Clustering, and SHAP Interpretability (Phase 4)

**Leakage prevention.** To maintain strict separation between training and test data, all unsupervised transformations (StandardScaler, PCA, K-Means) were fit exclusively on non-holdout rows. The union of all four targets' Phase 3 test indices was excluded from the fitting set. Test rows were then projected into the learned PCA space and assigned to the learned cluster centroids using `transform()` and `predict()`, never `fit_transform()` or `fit_predict()`. SHAP values were computed on the exact Phase 3 holdout rows loaded from saved artifacts.

**PCA.** Principal Component Analysis was applied to the 14 standardized numeric predictor features. PC1 primarily reflected institutional resources, tuition, grant aid, and affordability. PC2 reflected enrollment scale and borrowing/Pell-related student need. The first two components captured a meaningful fraction of total variance but not all of it, so the PCA visualization provides a simplified view of institutional diversity.

**K-Means Clustering.** K-Means clustering was performed for K = 2 through K = 10 on the non-holdout scaled features. K = 2 through K = 4 scored similarly on silhouette, so K = 4 was selected for interpretability rather than a decisive metric gap. Cluster labels were assigned programmatically from the profile table to prevent label drift across re-runs:

| Cluster Archetype | Key Characteristics |
|---|---|
| Large public / broad-access | Highest enrollment, high part-time share, lower tuition, moderate outcomes |
| Mixed mid-resource | Largest group; moderate tuition, aid, borrowing, and outcomes |
| Resource-rich private nonprofit | Highest tuition, highest grant aid, lowest student-faculty ratio, strongest outcomes |
| High-need / high-borrowing | Highest Pell share, highest loan participation, highest loan burden ratio, weakest outcomes |

**SHAP Interpretability.** TreeExplainer was used to compute SHAP values for each target's best model on the exact Phase 3 holdout set. SHAP summary plots, bar plots, waterfall plots, and dependence plots were generated. Cluster-specific SHAP analysis examined whether the drivers of predicted six-year graduation rate differed across the four institutional archetypes.

---

## 3. Integrated Findings by Research Question

### 3.1 Research Question 1: How does financial aid impact student outcomes?

Financial need and aid-related variables are among the strongest predictors of student outcomes across all models.

**Pell percentage is the dominant predictor.** Across all four targets, `pell_pct` has the highest mean absolute SHAP value and the highest permutation importance. Institutions with higher shares of Pell Grant recipients tend to have lower predicted graduation and retention rates. This should not be interpreted causally — Pell percentage likely captures broader socioeconomic conditions, student financial need, and institutional resource challenges rather than a direct effect of Pell enrollment on outcomes.

**Aid structure matters.** The engineered `affordability_index` (institutional grant aid relative to average federal loan amount) appeared among the top SHAP predictors for graduation-related outcomes. Feature ablation confirmed that removing `affordability_index` reduced cross-validation R² by 0.007–0.009 for `grad_rate_6yr` and `grad_rate_total`. The cluster profiles reinforce this: the resource-rich private nonprofit cluster has the highest institutional grant aid and strongest outcomes, while the high-need/high-borrowing cluster has the highest loan burden ratio and weakest outcomes.

**Borrowing pressure is associated with weaker outcomes.** The cluster-specific SHAP analysis for the high-need/high-borrowing archetype showed that `loan_burden_ratio`, `avg_fed_loan`, and `affordability_index` were among the top feature drivers for predicted six-year graduation rate. This suggests that the interplay between borrowing and institutional aid is an important dimension of the model's predictions for the most financially stressed institutions.

### 3.2 Research Question 2: How do institutional factors influence student success?

Institutional characteristics play a substantial role in explaining graduation and retention variation, though the predictive ceiling highlights that institution-level features alone cannot fully account for outcomes.

**Instructional spending is consistently important.** `instr_exp_per_fte` is a top-three SHAP predictor for `grad_rate_6yr`, `grad_rate_total`, and `pell_grad_rate`, and a top-five predictor for `retention_rate`. Permutation importance confirms this: removing `instr_exp_per_fte` from the `grad_rate_total` model reduces R² by 0.10. Higher instructional spending per FTE is associated with stronger predicted outcomes.

**Enrollment structure shapes predictions.** `total_enroll` and `parttime_share` appear repeatedly among the top SHAP predictors. The PCA results support this: PC2 is primarily driven by enrollment scale variables. The large public/broad-access cluster, defined by the highest enrollment, shows moderate-to-strong outcomes, while institutions with high part-time shares tend to show weaker retention patterns.

**Selectivity contributes but does not dominate.** Admission rate is among the top permutation importance features for `grad_rate_total` (importance = 0.077) and appears in SHAP rankings for graduation-related targets. However, it is not the strongest predictor for any target. The descriptive comparisons show a clear selectivity gradient — highly selective institutions have the highest average outcomes — but the model results show that financial need, resources, and enrollment structure explain more variance than selectivity alone.

**The predictive ceiling is informative.** The best held-out R² values range from 0.31 (retention) to 0.55 (six-year graduation rate). Institution-level features explain roughly half the variation in graduation outcomes and less than a third for retention. The unexplained variance likely reflects student-level factors absent from the data: academic preparation, family background, work obligations, advising experiences, and personal circumstances. This ceiling should frame all recommendations — institutional characteristics are meaningfully associated with outcomes, but they are not the whole story.

### 3.3 Research Question 3: How do outcomes differ across institution types?

Student outcomes differ substantially across institutional categories, and data-driven clustering reveals archetypes that cut across simple categorical boundaries.

**Descriptive comparisons show clear gradients.** Private not-for-profit institutions show the strongest average graduation and retention outcomes, followed by public institutions, with private for-profit institutions showing the weakest. Highly selective institutions (<25% admission rate) outperform open-access institutions (>75%) across all targets. Locale differences (city, suburb, town, rural) are present but less pronounced.

**Clustering reveals richer archetypes.** The four K-Means clusters capture combinations of features that single-variable comparisons miss. The gap between the resource-rich private nonprofit cluster and the high-need/high-borrowing cluster is substantial across all outcome measures. The mixed mid-resource cluster is the largest group, reflecting the diversity of the U.S. higher education landscape.

**Different archetypes rely on different predictors.** The cluster-specific SHAP analysis shows that while `pell_pct` is universally important, the relative importance of other features varies. For the high-need/high-borrowing cluster, borrowing-related variables (`loan_burden_ratio`, `avg_fed_loan`) are prominent. For the resource-rich private nonprofit cluster, `affordability_index`, `instr_exp_per_fte`, and `inst_grant_aid` are more prominent. For the large public/broad-access cluster, `total_enroll` and `parttime_share` carry more weight. This means there is no single universal explanation for student success across all institution types.

---

## 4. Conclusions

This study demonstrates that student outcomes at U.S. four-year institutions are shaped by several overlapping factors: student financial need, institutional resources, affordability and aid structure, enrollment composition, selectivity, and institutional type. No single variable dominates — outcomes are best understood as the product of multiple interacting dimensions.

The analytical pipeline — from data cleaning and feature engineering through model comparison, clustering, and SHAP — provides a consistent and interpretable picture. PCA summarized the major dimensions of institutional variation. Clustering identified four meaningful institutional archetypes. Regression modeling quantified predictive performance. SHAP explained how specific features drive model predictions for different institution types.

**The predictive ceiling matters.** The best models explain approximately 49–55% of the variation in graduation rates and 31% of retention rate variation using institution-level features alone. This means that roughly half the story is captured by the institutional characteristics available in IPEDS, while the other half likely depends on student-level factors — academic preparation, socioeconomic background, family support, advising quality, and personal circumstances — that institution-level data cannot measure. All findings and recommendations below should be read in this light: the patterns are real but partial.

**Methodological integrity.** The corrected Phase 4 workflow addresses data leakage by loading exact Phase 3 holdout indices, fitting all unsupervised transformations (StandardScaler, PCA, K-Means) on non-holdout rows only, and computing SHAP values exclusively on true out-of-sample data. Cluster labels are assigned programmatically from the profile table to prevent narrative drift across re-runs. These corrections ensure that the reported R² values and SHAP rankings reflect genuine out-of-sample performance.

---

## 5. Policy and Institutional Recommendations

The following recommendations are framed as institutional and policy implications consistent with the observed patterns. They are associational rather than causal — the data show where outcomes are weakest and which factors the models identify as most important, but changing any single variable may not produce the predicted effect in isolation.

### Recommendation 1: Target instructional and advising investment at high-need institutions

Institutions in the high-need/high-borrowing cluster combine the highest Pell share with the weakest graduation and retention outcomes and comparatively lower instructional spending per FTE. The SHAP results show that `pell_pct` and `instr_exp_per_fte` are among the strongest model-based drivers of predicted graduation rates across all clusters. This suggests that targeted instructional and advising investment at high-need institutions — where student financial stress is greatest and outcomes are weakest — may be where additional support matters most.

*Evidence base:* High-need cluster profile (highest `pell_pct`, lowest `grad_rate_6yr`); permutation importance of `instr_exp_per_fte` (0.052 for `grad_rate_6yr`, 0.100 for `grad_rate_total`); cluster-specific SHAP showing `pell_pct` and `instr_exp_per_fte` as top drivers for this archetype.

### Recommendation 2: Strengthen institutional aid to offset borrowing pressure

The model results and cluster profiles consistently show that institutions with stronger institutional grant aid relative to student borrowing tend to have better predicted outcomes. The `affordability_index` (grant aid / average federal loan) contributed meaningful predictive gains in feature ablation testing. The high-need cluster has the highest `loan_burden_ratio` and weakest outcomes, while the resource-rich cluster has the highest `inst_grant_aid` and strongest outcomes.

Policy implications include directing institutional and state-level aid toward reducing the loan-to-grant ratio at institutions where borrowing pressure is highest. This does not mean that shifting dollars from loans to grants will mechanically improve graduation rates — but the pattern suggests that the structure of financial support, not just its total amount, is associated with student success.

*Evidence base:* Feature ablation showing `affordability_index` contributes R² improvement of 0.007–0.009; cluster contrast between resource-rich (highest `inst_grant_aid`, strongest outcomes) and high-need (highest `loan_burden_ratio`, weakest outcomes); SHAP dependence plots showing `affordability_index` among top predictors.

### Recommendation 3: Address the part-time enrollment challenge

Institutions with higher part-time enrollment shares face different retention and graduation dynamics. `parttime_share` appears among the top SHAP predictors for multiple targets, and feature ablation confirmed that removing it reduces cross-validation R² by 0.011–0.012 for graduation-related targets. The large public/broad-access cluster, which has the highest part-time share, shows moderate outcomes despite serving the largest student populations.

Institutions with high part-time shares may benefit from flexible scheduling, targeted advising for non-traditional students, and retention programs designed for students balancing work, family, and education. Policymakers should recognize that applying the same outcome benchmarks to institutions with very different enrollment compositions may not reflect the additional challenges these institutions face.

*Evidence base:* Permutation importance of `parttime_share` (0.032 for `grad_rate_6yr`, 0.039 for `grad_rate_total`); feature ablation delta; cluster profile showing large public/broad-access institutions with highest `parttime_share`.

---

## 6. Limitations

1. **Associational, not causal.** PCA, clustering, model performance, and SHAP values show patterns in the data. They do not prove that changing one feature would directly cause graduation or retention rates to change. All findings describe model-based associations.

2. **Institution-level data only.** The dataset does not include student-level factors such as academic preparation, family background, work obligations, advising experiences, or personal challenges. The predictive ceiling (R² = 0.31–0.55) reflects this limitation — roughly half the variation in outcomes is not captured by institutional characteristics alone.

3. **Clustering is approximate.** K = 2 through K = 4 produced similar silhouette scores, so K = 4 was selected for interpretability. The modest silhouette score means the clusters are broad archetypes with overlapping boundaries, not perfectly separated categories.

4. **SHAP explains the model, not reality.** SHAP values show how the trained models use features to make predictions. They do not independently prove real-world causal relationships. Feature importance rankings depend on the model, the features included, and the data.

5. **Sparse one-hot state features.** Categorical state variables are one-hot encoded. Individual state dummies appearing among top SHAP features may reflect a small subset of institutions in the holdout set rather than a broad geographic effect. These features should be interpreted cautiously.

6. **Cluster-specific SHAP uses small subgroups.** When the holdout set is partitioned by cluster, some subgroups contain relatively few institutions. Cluster-specific SHAP patterns should be treated as subgroup-level model explanations rather than definitive findings.

7. **Phase 3/Phase 4 split reconciliation.** The Phase 3 models were retrained on the current cleaned dataset (2,716 institutions), and the exact train and test indices were saved as joblib artifacts. Phase 4 loads these saved indices rather than calling `train_test_split` again, which prevents the data leakage identified in the initial Phase 4 version where re-splitting on a changed dataset caused training rows to leak into the test set. All unsupervised transformations in Phase 4 (StandardScaler, PCA, K-Means) are fit exclusively on non-holdout rows.

---

## References

- IPEDS (Integrated Postsecondary Education Data System), National Center for Education Statistics, U.S. Department of Education, 2022.
- Phase 1 Notebook: Data Preprocessing and Exploratory Data Analysis
- Phase 2/3 Notebook: Feature Engineering, Regression Modeling, and Model Selection
- Phase 4 Notebook: PCA, Clustering, and SHAP Interpretability (Corrected)
