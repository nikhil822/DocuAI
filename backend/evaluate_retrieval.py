
import json

from retrieval import retrieve_chunks


TOP_K = 8


def main():
    with open("eval_questions.json", encoding="utf-8") as file:
        questions = json.load(file)

    if not questions:
        print("No evaluation questions found.")
        return

    hits = 0

    for index, item in enumerate(questions, start=1):
        results = retrieve_chunks(item["question"], top_k=TOP_K)

        expected_document = item["expected_document"]
        expected_pages = set(item["expected_pages"])

        
        expected_terms = item["expected_answer_terms"]

        hit = any(
            result["document_name"] == expected_document
            and result["page_number"] in expected_pages
            and any(
                term.casefold() in result["text"].casefold()
                for term in expected_terms
            )
            for result in results
        )

        hits += int(hit)

        
        print(f"\nQuestion {index}: {item['question']}")
        print("Expected document:", item["expected_document"])
        print("Expected pages:", item["expected_pages"])
        print("Expected terms:", item["expected_answer_terms"])

        for rank, result in enumerate(results, start=1):
            print(
                f"  Rank {rank}: "
                f"{result['document_name']} "
                f"page={result['page_number']} "
                f"score={result['similarity']:.4f}"
            )
            print("   ", result["text"][:200].replace("\n", " "))

        print("Result:", "HIT" if hit else "MISS")


    recall_at_8 = hits / len(questions)

    print("\n--- Evaluation summary ---")
    print(f"Questions: {len(questions)}")
    print(f"Hits: {hits}")
    print(f"Misses: {len(questions) - hits}")
    print(f"Recall@{TOP_K}: {recall_at_8:.1%}")


if __name__ == "__main__":
    main()
