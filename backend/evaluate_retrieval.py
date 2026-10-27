
import json
from pathlib import Path

from retrieval import retrieve_chunks

TOP_K = 8
DATASET_PATH = Path(__file__).with_name("eval_questions.json")


def is_relevant(result: dict, item: dict) -> bool:
    expected_document = item["expected_document"]
    expected_pages = set(item["expected_pages"])
    expected_terms = item["expected_answer_terms"]

    return (
        result["document_name"] == expected_document
        and result["page_number"] in expected_pages
        and any(
            term.casefold() in result["text"].casefold()
            for term in expected_terms
        )
    )


def reciprocal_rank(results: list[dict], item: dict) -> float:
    for rank, result in enumerate(results, start=1):
        if is_relevant(result, item):
            return 1.0 / rank

    return 0.0


def main():
    with DATASET_PATH.open(encoding="utf-8") as file:
        questions = json.load(file)

    if not questions:
        print("No evaluation questions found.")
        return

    hits = 0
    reciprocal_ranks = []
    misses = []

    for index, item in enumerate(questions, start=1):
        results = retrieve_chunks(
            item["question"],
            top_k=TOP_K,
        )

        hit = any(is_relevant(result, item) for result in results)
        hits += int(hit)

        rr = reciprocal_rank(results, item)
        reciprocal_ranks.append(rr)

        
        if not hit:
            print("\n--- MISS DIAGNOSTICS ---")
            print("Question:", item["question"])
            print("Expected document:", item["expected_document"])
            print("Expected pages:", item["expected_pages"])
            print("Expected terms:", item["expected_answer_terms"])

            for rank, result in enumerate(results, start=1):
                print(
                    f"\nRank {rank} | "
                    f"{result['document_name']} | "
                    f"page {result['page_number']} | "
                    f"similarity={result['similarity']:.4f}"
                )
                print(result["text"][:500].replace("\n", " "))


        first_relevant_rank = next(
            (
                rank
                for rank, result in enumerate(results, start=1)
                if is_relevant(result, item)
            ),
            None,
        )

        print(
            f"{index:02d}. "
            f"{'HIT' if hit else 'MISS'} | "
            f"first relevant rank={first_relevant_rank} | "
            f"RR={rr:.3f} | "
            f"{item['question']}"
        )

    total = len(questions)
    hit_rate = hits / total
    mrr = sum(reciprocal_ranks) / total

    print("\n--- Retrieval evaluation ---")
    print(f"Questions:  {total}")
    print(f"Hits:       {hits}")
    print(f"Misses:     {total - hits}")
    print(f"HitRate@{TOP_K}: {hit_rate:.1%}")
    print(f"MRR@{TOP_K}:     {mrr:.3f}")

    if misses:
        print("\nQuestions to investigate:")
        for question in misses:
            print(f"- {question}")


if __name__ == "__main__":
    main()
