# %%
from occ_tests_common import *

import os
import occ_datasets
import scipy.stats
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn import metrics

from pyod.models.ecod import ECOD
from ecod_v2 import ECODv2
from ecod_v2_min import ECODv2Min
from sklearn.svm import OneClassSVM
from sklearn.ensemble import IsolationForest

n_repeats = 10
resampling_repeats = 10

# datasets = [(dataset, 'mat') for dataset in occ_datasets.MAT_DATASETS] + \
#     [(dataset, 'arff') for dataset in occ_datasets.ARFF_DATASETS]

datasets = [
    # .mat
    ('Arrhythmia', 'mat'),
    ('Breastw', 'mat'),
    ('Cardio', 'mat'),
    ('Ionosphere', 'mat'),
    ('Lympho', 'mat'),
    ('Mammography', 'mat'),
    ('Optdigits', 'mat'),
    ('Pima', 'mat'),
    ('Satellite', 'mat'),
    ('Satimage-2', 'mat'),
    ('Shuttle', 'mat'),
    ('Speech', 'mat'),
    ('WBC', 'mat'),
    ('Wine', 'mat'),
    # .arff
    ('Arrhythmia', 'arff'),
    ('Cardiotocography', 'arff'),
    ('HeartDisease', 'arff'),
    ('Hepatitis', 'arff'),
    ('InternetAds', 'arff'),
    ('Ionosphere', 'arff'),
    ('KDDCup99', 'arff'),
    ('Lymphography', 'arff'),
    ('Pima', 'arff'),
    ('Shuttle', 'arff'),
    ('SpamBase', 'arff'),
    ('Stamps', 'arff'),
    ('Waveform', 'arff'),
    ('WBC', 'arff'),
    ('WDBC', 'arff'),
    ('WPBC', 'arff'),
]
# datasets = [
#     ('Speech', 'mat'),
#     # ('KDDCup99', 'arff'),
# ]

for alpha in [0.05, 0.25, 0.5]:
    full_results = []

    RESULTS_DIR = f'results_fnr_{alpha:.2f}'
    os.makedirs(RESULTS_DIR, exist_ok=True)

    for (dataset, format) in datasets:
        results = []

        for exp in range(n_repeats):
            # Load data
            X, y = occ_datasets.load_dataset(dataset, format)
            X_train_orig, X_test_orig, y_test_orig = occ_datasets.split_occ_dataset(X, y, train_ratio=0.6)

            # include only inliers
            inliers = np.where(y_test_orig == 1)[0]
            y_test_orig = y_test_orig[inliers]
            X_test_orig = X_test_orig[inliers, :]

            for baseline in [
                # 'ECOD',
                'ECODv2',
                # 'ECODv2Min',
                # 'GeomMedian',
                'Mahalanobis',
                # 'OC-SVM',
                # 'IForest',
            ]:
                for pca_variance_threshold in [0.5, 0.9, 1.0, None]:
                    X_train, X_test, y_test = X_train_orig, X_test_orig, y_test_orig
                    if pca_variance_threshold is not None:
                        if not 'ECODv2' in baseline and not 'Mahalanobis' in baseline:
                            continue
                        X_train, X_test, _ = PCA_by_variance(X_train, X_test, pca_variance_threshold)

                    if baseline == 'ECOD':
                        clf = PyODWrapper(ECOD())
                    elif baseline == 'ECODv2':
                        clf = PyODWrapper(ECODv2())
                    elif baseline == 'ECODv2Min':
                        clf = PyODWrapper(ECODv2Min())
                    elif baseline == 'GeomMedian':
                        clf = GeomMedianDistance()
                    elif baseline == 'Mahalanobis':
                        clf = Mahalanobis()
                    elif baseline == 'OC-SVM':
                        clf = OneClassSVM()
                    elif baseline == 'IForest':
                        clf = IsolationForest()
                    
                    for cutoff_type in [
                        'Multisplit'
                    ]:
                        if cutoff_type != 'Empirical' and not 'ECODv2' in baseline and not 'Mahalanobis' in baseline:
                            continue
                        
                        N = len(X_train)
                        if cutoff_type == 'Multisplit':
                            cal_scores_all = np.zeros((resampling_repeats, N - int(N/2)))
                            for i in range(resampling_repeats):
                                multisplit_samples = np.random.choice(range(N), size=int(N/2), replace=False)
                                is_multisplit_sample = np.isin(range(N), multisplit_samples)
                                X_multi_train, X_multi_cal = X_train[is_multisplit_sample], X_train[~is_multisplit_sample]
                                
                                clf.fit(X_multi_train)
                                cal_scores = clf.score_samples(X_multi_cal)
                                cal_scores_all[i, :] = cal_scores

                        clf.fit(X_train)

                        scores = clf.score_samples(X_test)

                        if cutoff_type == 'Multisplit':
                            p_vals_all = np.zeros((resampling_repeats, len(scores)))
                            for i in range(resampling_repeats):
                                cal_scores = cal_scores_all[i, :]
                                num_smaller_cal_scores = (scores > cal_scores.reshape(-1, 1)).sum(axis=0)
                                p_vals = (num_smaller_cal_scores + 1) / (len(cal_scores) + 1)
                                p_vals_all[i, :] = p_vals
                            p_vals = 2 * np.median(p_vals_all, axis=0)
                            y_pred = np.where(p_vals < alpha, 0, 1)
                    
                        fnr = 1 - np.mean(y_pred == y_test) # False Negative Rate

                        print(f'{dataset}.{format}: {baseline}{f"+PCA{pca_variance_threshold:.1f}" if pca_variance_threshold is not None else ""} ({cutoff_type}, {exp+1}/{n_repeats})' + \
                            f' ||| FNR: {fnr:.3f}')
                        occ_metrics = {
                            'Dataset': f'({format}) {dataset}',
                            'Method': baseline + (f"+PCA{pca_variance_threshold:.1f}" if pca_variance_threshold is not None else ""),
                            'Cutoff': cutoff_type,
                            'Exp': exp + 1,
                            'alpha': alpha,
                            'FNR': fnr,
                        }
                        results.append(occ_metrics)
                        full_results.append(occ_metrics)
        
        df = pd.DataFrame.from_records(results)

        dataset_df = df[df.Dataset == f'({format}) {dataset}']
        res_df = dataset_df.groupby(['Dataset', 'Method', 'Cutoff', 'alpha'])\
            [['FNR']] \
            .mean() \
            .round(3)

        res_df = append_mean_row(res_df)
        display(res_df)
        res_df.to_csv(os.path.join(RESULTS_DIR, f'dataset-{format}-{dataset}.csv'))

    # Full result pivots
    df = pd.DataFrame.from_records(full_results)
    df

    pivots = {}
    for metric in ['FNR', 'alpha']:
        metric_df = df
        
        pivot = metric_df \
            .pivot_table(values=metric, index=['Dataset'], columns=['Method', 'Cutoff'], dropna=False) \
            * 1
        
        pivots[metric] = pivot
        pivot = append_mean_row(pivot)

        if metric in ['alpha']:
            continue
        
        pivot \
            .round(3) \
            .to_csv(os.path.join(RESULTS_DIR, f'dataset-all-{metric}.csv'))

    append_mean_row(pivots['FNR'] < pivots['alpha']).to_csv(os.path.join(RESULTS_DIR, f'dataset-all-FNR-alpha.csv'))

# %%
