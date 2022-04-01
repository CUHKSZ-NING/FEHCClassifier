import numpy as np
from sklearn.tree import DecisionTreeClassifier as DT
from copy import deepcopy
# from sklearn.metrics import confusion_matrix, accuracy_score
from imblearn.ensemble import BalancedBaggingClassifier as BBC
from Individual import Individual
import random
import math


class EvolutionaryHMC(object):
    def __init__(self, base_estimators=None, n_estimators=10, population=10, iteration=10, dropout=0, verbose=True,
                 dynamic_classifier=True, dynamic_feature=True, dynamic_hierarchical=True, gamma=0.2):
        if base_estimators is None:
            self.base_estimators_ = {'DT': DT()}
        else:
            self.base_estimators_ = base_estimators
        self.n_estimators_ = n_estimators
        self.population_ = population
        self.iteration_ = iteration
        self.dropout_ = dropout
        self.verbose_ = verbose
        self.dynamic_classifier_ = dynamic_classifier
        self.dynamic_feature_ = dynamic_feature
        self.dynamic_hierarchical_ = dynamic_hierarchical
        self.gamma_ = gamma
        self.ga_result = {
            'tree': {},
            'split': {},
            'feature': {},
            'clf': {}
        }

    def fit(self, X, y):
        name_base_estimators = {}
        index = 0
        for key in self.base_estimators_:
            name_base_estimators[index] = key
            index += 1

        feature_dim = len(X[0, ...])
        node = []
        # label_pred = np.zeros(len(label_test), dtype=int)
        class_map = []
        for i in range(0, max(y) + 1):
            class_map.append(int(i))

        # label_dim = len(X[0, ...])

        for i in range(0, len(class_map)):
            if i in class_map:
                node.append(0)
            else:
                node.append(-1)

        for p in range(0, len(class_map) - 1):
            if self.verbose_:
                print('Split %d:' % p)
                print('----------------')

            label_next, label_count = get_label_next(node)

            individuals = None

            for q in range(0, self.iteration_):
                progress = q / self.iteration_

                if individuals is None:
                    individuals = []

                    features_droped = np.zeros(feature_dim)
                    random_order = np.array(random.sample(range(0, feature_dim), feature_dim))
                    drop_indices = random_order[range(0, math.ceil(feature_dim * self.dropout_))]
                    features_droped[drop_indices] = 1

                    for i in range(0, self.population_):
                        individual = Individual(num_base_estimators=len(self.base_estimators_),
                                                dynamic_classifier=self.dynamic_classifier_,
                                                dynamic_feature=self.dynamic_feature_,
                                                dynamic_hierarchical=self.dynamic_hierarchical_, gamma=self.gamma_)
                        individual.initialize(feature_dim, node, label_next, features_droped=features_droped)
                        individual.get_fitness(X, y, self.base_estimators_)
                        individual.rate_update(label_count, progress)
                        individuals.append(individual)

                else:
                    new_individuals = []
                    elite_ratio = 0.3 * math.exp(-progress)
                    elite_count = int(self.population_ * elite_ratio)

                    for i in range(0, self.population_ - elite_count):
                        fine_index = random.randint(0, int(self.population_ * 0.5 - 1))
                        other_index = random.randint(0, self.population_ - 1)
                        new_individual = individuals[fine_index].cross_over(individuals[other_index])
                        new_individuals.append(new_individual)

                    for i in range(elite_count, self.population_):
                        index = i - elite_count
                        individuals[i] = deepcopy(new_individuals[index])

                    new_individuals.clear()

                    # mutate
                    for i in range(0, self.population_):
                        individuals[i].rate_update(label_count, progress)
                        individuals[i].mutate()

                    for i in range(0, self.population_):
                        individuals[i].get_fitness(X, y, self.base_estimators_)

                individuals.sort(key=lambda item: item.fitness, reverse=True)

                # print(individuals[0].chromosome['label'])

                class_id_0 = []
                class_id_1 = []

                if self.verbose_:
                    print('--Iter %d--' % q)

                for i in range(0, len(individuals[0].chromosome['label'])):
                    if individuals[0].chromosome['label'][i] == 0:
                        class_id_0.append(i)
                    if individuals[0].chromosome['label'][i] == 1:
                        class_id_1.append(i)

                if self.verbose_:
                    print(class_id_0, 'vs', class_id_1, '\n')

                if self.verbose_:
                    print('> Val: \n%.2f -- %.2f%% <---- %s\n' %
                          (100 * individuals[0].fitness, 100 * individuals[0].accuracy,
                           name_base_estimators[individuals[0].chromosome['clf']]))

            for i in range(0, len(individuals[0].chromosome['label'])):
                if individuals[0].chromosome['label'][i] == 1:
                    node[i] = p + 1

            self.ga_result['tree'][p] = deepcopy(node)
            self.ga_result['split'][p] = deepcopy([label_next, p + 1])
            self.ga_result['feature'][p] = deepcopy(individuals[0].chromosome['feature'])

            base_model = self.base_estimators_[name_base_estimators[individuals[0].chromosome['clf']]]
            model = BBC(base_estimator=deepcopy(base_model), n_estimators=10)
            class_0 = np.where(np.array(self.ga_result['tree'][p]) == self.ga_result['split'][p][0])[0]
            class_1 = np.where(np.array(self.ga_result['tree'][p]) == self.ga_result['split'][p][1])[0]
            # print(class_0, 'vs', class_1, '\n')
            X_new = None
            y_new = None
            for label in class_0:
                X_i = deepcopy(X[np.where(y == label)])
                X_i = X_i[..., np.where(self.ga_result['feature'][p] == 1)[0]]
                if X_new is None:
                    X_new = deepcopy(X_i)
                    y_new = np.zeros(len(X_i), dtype=int)
                else:
                    X_new = np.concatenate((X_new, X_i))
                    y_new = np.concatenate((y_new, np.zeros(len(X_i), dtype=int)))
            for label in class_1:
                X_i = deepcopy(X[np.where(y == label)])
                X_i = X_i[..., np.where(self.ga_result['feature'][p] == 1)[0]]
                X_new = np.concatenate((X_new, X_i))
                y_new = np.concatenate((y_new, np.ones(len(X_i), dtype=int)))
            model.fit(X_new, y_new)
            self.ga_result['clf'][p] = deepcopy(model)

            individuals.clear()

    def predict(self, X_test):
        y_pred = np.zeros(len(X_test), dtype=int)

        for p in range(0, len(self.ga_result['tree'])):
            y_pred_p = self.ga_result['clf'][p].predict(X_test[..., np.where(self.ga_result['feature'][p] == 1)[0]])
            for i in range(0, len(y_pred)):
                if y_pred[i] == self.ga_result['split'][p][0] and y_pred_p[i] == 1:
                    y_pred[i] = self.ga_result['split'][p][1]

        mapping = {}
        for p in range(0, len(self.ga_result['tree']) + 1):
            mapping[p] = np.where(y_pred == self.ga_result['tree'][len(self.ga_result['tree']) - 1][p])
        for p in range(0, len(self.ga_result['tree']) + 1):
            y_pred[mapping[p]] = p

        return y_pred


class EvolutionarySAE(object):
    def __init__(self, base_estimators=None, n_estimators=30, population=5, iteration=2, dropout=0, verbose=True,
                 dynamic_classifier=True, dynamic_feature=True, dynamic_hierarchical=True, gamma=0.2):
        # def __init__(self, base_estimators=None, n_estimators=1, population=5, iteration=1, dropout=0, verbose=True,
        #              dynamic_classifier=True, dynamic_feature=True, dynamic_hierarchical=True):
        if base_estimators is None:
            self.base_estimators_ = {'DT': DT()}
        else:
            self.base_estimators_ = base_estimators
        self.n_estimators_ = n_estimators
        self.population_ = population
        self.iteration_ = iteration
        self.dropout_ = dropout
        self.verbose_ = verbose
        self.dynamic_classifier_ = dynamic_classifier
        self.dynamic_feature_ = dynamic_feature
        self.dynamic_hierarchical_ = dynamic_hierarchical
        self.gamma_ = gamma
        self.EHMCs = {}
        self.num_classes = -1

    def fit(self, X, y):
        self.num_classes = max(y) + 1
        for i in range(0, self.n_estimators_):
            EHMC = EvolutionaryHMC(base_estimators=self.base_estimators_, n_estimators=self.n_estimators_,
                                   population=self.population_, iteration=self.iteration_, dropout=self.dropout_,
                                   verbose=self.verbose_, dynamic_classifier=self.dynamic_classifier_,
                                   dynamic_feature=self.dynamic_feature_,
                                   dynamic_hierarchical=self.dynamic_hierarchical_, gamma=self.gamma_)
            EHMC.fit(X, y)
            self.EHMCs[i] = deepcopy(EHMC)

    def predict(self, X_test, n_test_estimators=0):
        y_pred_proba = self.predict_proba(X_test, n_test_estimators=n_test_estimators)
        y_predict = np.zeros(len(y_pred_proba), dtype=int)
        for i in range(0, len(y_predict)):
            target = np.where(y_pred_proba[i] == max(y_pred_proba[i]))[0]
            try:
                y_predict[i] = target[random.randint(0, len(target) - 1)]
            except IndexError:
                pass
        return y_predict

    def predict_proba(self, X_test, n_test_estimators=0):
        if n_test_estimators == 0:
            n_test_estimators = len(self.EHMCs)
        y_pred_proba = np.zeros((len(X_test), self.num_classes))
        for i in range(0, n_test_estimators):
            y_pred_i = self.EHMCs[i].predict(X_test)
            for j in range(0, len(X_test)):
                y_pred_proba[j][y_pred_i[j]] += 1
        y_pred_proba /= n_test_estimators

        return y_pred_proba


def get_label_next(node):
    class_number = np.zeros(max(node) + 1, dtype=int)
    label_next = -1
    label_count = -1

    for i in range(0, len(node)):
        if node[i] != -1:
            class_number[node[i]] += 1

    for i in range(0, len(class_number)):
        if class_number[i] >= 2:
            label_next = i
            label_count = class_number[i]

            break

    return label_next, label_count
