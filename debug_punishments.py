import asyncio
import database as db
import aiosqlite

async def debug_punishments():
    dominant_id = 303302808903057410  # Your Discord ID
    
    print("=== Checking all punishment assignments ===")
    async with aiosqlite.connect(db.DATABASE_NAME) as database:
        database.row_factory = aiosqlite.Row
        
        # Get ALL punishment assignments
        async with database.execute("""
            SELECT ap.id, ap.dominant_id, ap.completion_status, ap.submitted_at, 
                   p.title, u.username as submissive_name
            FROM assigned_rewards_punishments ap
            JOIN punishments p ON ap.item_id = p.id
            JOIN users u ON ap.submissive_id = u.user_id
            WHERE ap.type = 'punishment'
            ORDER BY ap.id DESC
        """) as cursor:
            all_assignments = await cursor.fetchall()
            print(f"\nTotal punishment assignments: {len(all_assignments)}")
            for row in all_assignments:
                print(f"  ID: {row['id']}, Status: {row['completion_status']}, "
                      f"Dominant: {row['dominant_id']}, Title: {row['title']}, "
                      f"Sub: {row['submissive_name']}, Submitted: {row['submitted_at']}")
    
    print(f"\n=== Checking autocomplete query for dominant {dominant_id} ===")
    pending_items = await db.get_pending_punishment_assignments_for_autocomplete(dominant_id)
    print(f"Autocomplete returned: {len(pending_items)} items")
    for item in pending_items:
        print(f"  {item}")
    
    print("\n=== Checking get_pending_punishments function ===")
    pending_punishments = await db.get_pending_punishments(dominant_id)
    print(f"get_pending_punishments returned: {len(pending_punishments)} items")
    for pun in pending_punishments:
        print(f"  {pun}")

if __name__ == "__main__":
    asyncio.run(debug_punishments())
