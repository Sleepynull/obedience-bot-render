# Obedience Bot - Recent Changes

## New Features Added (February 2026)

### 1. Specific Datetime Deadlines
You can now set exact deadline dates/times instead of just relative hours.

**Commands Updated:**
- `/task_add` - New parameter: `deadline_datetime`
- `/punishment_assign` - New parameter: `deadline_datetime`
- `/punishment_assign_random` - New parameter: `deadline_datetime`

**Format:** `YYYY-MM-DD HH:MM` (24-hour format)
**Example:** `2026-02-05 15:30` (February 5th, 2026 at 3:30 PM)

**Usage:**
```
/task_add submissive:@User title:"Daily workout" description:"30 min cardio" 
          frequency:Daily deadline_datetime:"2026-02-05 15:30"
```

**Note:** If both `deadline_datetime` and `deadline_hours` are provided, `deadline_datetime` takes priority.

### 2. Automatic Random Punishment on Missed Deadlines
Tasks can now automatically assign a random punishment when deadlines are missed.

**New Parameter:** `/task_add` now has `auto_punish` (boolean, default: False)

**How It Works:**
1. Set `auto_punish:True` when creating a task with a deadline
2. If the submissive misses the deadline, the system automatically:
   - Deducts the task points
   - Assigns a random punishment from the dominant's punishment list
   - Notifies both the dominant and submissive

**Requirements:**
- The dominant must have at least one punishment created
- The task must have a deadline set (either `deadline_hours` or `deadline_datetime`)

**Usage:**
```
/task_add submissive:@User title:"Morning routine" description:"Complete before noon" 
          frequency:Daily deadline_datetime:"2026-02-04 12:00" auto_punish:True
```

### 3. Enhanced Deadline Tracking
The existing deadline checking system (`check_deadlines` task loop) now supports:
- Specific datetime deadlines
- Random punishment assignment (when `auto_punishment_id` is set to `-1`)
- Better notifications showing punishment titles when auto-assigned

## Technical Details

### Database Changes
- Modified `tasks` table to support `auto_punishment_id` with special value `-1` for random punishment
- Existing columns remain unchanged - backward compatible

### Modified Functions
- `bot.py::task_add()` - Added `deadline_datetime` and `auto_punish` parameters
- `bot.py::punishment_assign()` - Added `deadline_datetime` parameter
- `bot.py::punishment_assign_random()` - Added `deadline_datetime` parameter
- `bot.py::check_deadlines()` - Enhanced to handle random punishment assignment
- `database.py::create_task()` - Added `auto_punishment_id` parameter

### Backward Compatibility
All changes are backward compatible:
- Existing tasks without deadlines continue to work
- `deadline_hours` parameter still works as before
- New features are opt-in via new parameters

## Examples

### Example 1: Task with specific deadline
```
/task_add submissive:@SubUser title:"Weekly report" description:"Submit by Friday 5pm" 
          frequency:Weekly deadline_datetime:"2026-02-07 17:00" points:25
```

### Example 2: Task with auto-punishment
```
/task_add submissive:@SubUser title:"Bedtime routine" description:"Complete by 10pm" 
          frequency:Daily deadline_datetime:"2026-02-04 22:00" 
          points:10 auto_punish:True
```

### Example 3: Punishment with specific deadline
```
/punishment_assign submissive:@SubUser punishment_id:5 
                   reason:"Missed deadline" 
                   deadline_datetime:"2026-02-05 18:00" 
                   point_penalty:20
```

## Testing Recommendations

1. Test specific datetime deadline parsing with various formats
2. Verify auto-punishment triggers correctly when deadline passes
3. Ensure random punishment selection works when multiple punishments exist
4. Check notifications contain correct information
5. Verify backward compatibility with existing tasks using `deadline_hours`
