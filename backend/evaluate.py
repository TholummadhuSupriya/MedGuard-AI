from sklearn.metrics import precision_score, recall_score, f1_score, confusion_matrix


def evaluate_medication_safety(y_true, y_pred):
    if len(y_true) != len(y_pred):
        raise ValueError("Input lists must have equal lengths.")

    print("\n=== MEDGUARD AI EVALUATION ===")
    print(f"Precision: {precision_score(y_true, y_pred, zero_division=0):.4f}")
    print(f"Recall:    {recall_score(y_true, y_pred, zero_division=0):.4f}")
    print(f"F1 Score:  {f1_score(y_true, y_pred, zero_division=0):.4f}")
    print("\nConfusion Matrix:")
    print(confusion_matrix(y_true, y_pred, labels=[0, 1]))


if __name__ == "__main__":
    # Temporary test data only, not real project results.
    evaluate_medication_safety(
        y_true=[1, 1, 0, 1, 0],
        y_pred=[1, 0, 0, 1, 0],
    )