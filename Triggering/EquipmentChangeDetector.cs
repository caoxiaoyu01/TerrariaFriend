#nullable enable

using System;
using System.Collections.Generic;
using TerrariaFriend.GameState.Snapshots;

namespace TerrariaFriend.Triggering
{
	// 仅跟踪护甲与配饰 手持物品切换不会触发装备事件
	public sealed class EquipmentChangeDetector
	{
		private EquipmentProjection? _previous;

		public bool TryDetect(
			GameSnapshot snapshot,
			out GameEvent? gameEvent,
			out GameEventContext? eventContext)
		{
			EquipmentProjection current = EquipmentProjection.Capture(snapshot.Inventory);
			if (_previous == null)
			{
				_previous = current;
				gameEvent = null;
				eventContext = null;
				return false;
			}

			EquipmentProjection previous = _previous;
			_previous = current;

			bool armorChanged = previous.Armor != current.Armor;
			(ItemSummary[] added, ItemSummary[] removed) = DiffAccessories(
				previous.Accessories,
				current.Accessories);
			if (!armorChanged && added.Length == 0 && removed.Length == 0)
			{
				gameEvent = null;
				eventContext = null;
				return false;
			}

			gameEvent = new GameEvent(GameEventType.EquipmentChanged);
			eventContext = new GameEventContext(
				ArmorBefore: armorChanged ? previous.Armor : null,
				ArmorAfter: armorChanged ? current.Armor : null,
				AccessoriesAdded: added,
				AccessoriesRemoved: removed);
			return true;
		}

		public void Reset()
		{
			_previous = null;
		}

		private static (ItemSummary[] Added, ItemSummary[] Removed) DiffAccessories(
			IReadOnlyList<ItemSummary> previous,
			IReadOnlyList<ItemSummary> current)
		{
			Dictionary<ItemKey, int> previousCounts = Count(previous);
			Dictionary<ItemKey, int> currentCounts = Count(current);
			List<ItemSummary> added = new List<ItemSummary>();
			List<ItemSummary> removed = new List<ItemSummary>();

			foreach (ItemSummary item in current)
			{
				ItemKey key = new ItemKey(item.TypeId, item.Stack);
				if (TakeOne(previousCounts, key)) continue;
				added.Add(item);
			}

			foreach (ItemSummary item in previous)
			{
				ItemKey key = new ItemKey(item.TypeId, item.Stack);
				if (TakeOne(currentCounts, key)) continue;
				removed.Add(item);
			}

			Comparison<ItemSummary> comparison = (left, right) =>
			{
				int typeComparison = left.TypeId.CompareTo(right.TypeId);
				if (typeComparison != 0) return typeComparison;
				int stackComparison = left.Stack.CompareTo(right.Stack);
				return stackComparison != 0
					? stackComparison
					: string.CompareOrdinal(left.Name, right.Name);
			};
			added.Sort(comparison);
			removed.Sort(comparison);
			return (added.ToArray(), removed.ToArray());
		}

		private static Dictionary<ItemKey, int> Count(IReadOnlyList<ItemSummary> items)
		{
			Dictionary<ItemKey, int> counts = new Dictionary<ItemKey, int>();
			foreach (ItemSummary item in items)
			{
				ItemKey key = new ItemKey(item.TypeId, item.Stack);
				counts.TryGetValue(key, out int count);
				counts[key] = count + 1;
			}
			return counts;
		}

		private static bool TakeOne(Dictionary<ItemKey, int> counts, ItemKey key)
		{
			if (!counts.TryGetValue(key, out int count) || count == 0) return false;
			counts[key] = count - 1;
			return true;
		}

		private sealed record EquipmentProjection(
			ArmorSnapshot Armor,
			IReadOnlyList<ItemSummary> Accessories)
		{
			public static EquipmentProjection Capture(InventorySnapshot inventory)
			{
				return new EquipmentProjection(
					inventory.Armor,
					new List<ItemSummary>(inventory.Accessories).ToArray());
			}
		}

		private readonly record struct ItemKey(int TypeId, int Stack);
	}
}
