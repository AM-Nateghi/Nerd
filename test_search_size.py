import asyncio
from tools import search_web


async def main():
    print("Testing optimized search_web output size...")
    result = await search_web("imdb rating for Blood Free film", num_results=2)

    with open("search_output.txt", "w", encoding="utf-8") as f:
        f.write(result)

    print(f"\n{'='*60}")
    print(f"Output length: {len(result)} characters")
    print(f"Estimated tokens: ~{len(result) // 4}")
    print(f"{'='*60}\n")
    print("Preview (first 500 chars):")
    print(result[:500])
    print("\n[...]\n")


if __name__ == "__main__":
    asyncio.run(main())
