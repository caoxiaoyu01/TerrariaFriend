#nullable enable

using System;
using System.Collections.Generic;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;
using Terraria.ModLoader.Default;
using TerrariaFriend.GameState.Snapshots;

namespace TerrariaFriend.GameState.Collectors
{
	public static class InventoryCollector
	{
		private const int HotbarSlots = 10;
		private const int MainInventorySlots = 50;

		private static readonly HashSet<int> BossSummonItemTypes = new HashSet<int>
		{
			ItemID.SlimeCrown,
			ItemID.SuspiciousLookingEye,
			ItemID.WormFood,
			ItemID.BloodySpine,
			ItemID.Abeemination,
			ItemID.DeerThing,
			ItemID.QueenSlimeCrystal,
			ItemID.MechanicalWorm,
			ItemID.MechanicalEye,
			ItemID.MechanicalSkull,
			ItemID.LihzahrdPowerCell,
			ItemID.TruffleWorm,
			ItemID.CelestialSigil,
			ItemID.GuideVoodooDoll,
			ItemID.EmpressButterfly
		};

		// 只收集快捷栏 装备和常用消耗品 不复制整个背包
		public static InventorySnapshot Capture(Player player)
		{
			HotbarSlotSummary[] hotbar = CaptureHotbar(player);
			ArmorSnapshot armor = CaptureArmor(player);
			ItemSummary[] accessories = CaptureAccessories(player);

			int totalHealingItemCount = 0;
			int bestHealingAmount = 0;
			ItemSummary? bestHealingItem = null;
			int totalManaItemCount = 0;
			int bestManaAmount = 0;
			ItemSummary? bestManaItem = null;
			int freeSlots = 0;
			Dictionary<int, ItemSummary> bossSummons = new Dictionary<int, ItemSummary>();

			// 空位只统计背包前五十格 不包含金币和弹药等专用栏位
			for (int slot = 0; slot < MainInventorySlots; slot++)
			{
				Item item = player.inventory[slot];
				if (item.IsAir)
				{
					freeSlots++;
					continue;
				}

				ItemSummary summary = CreateItemSummary(item);
				if (item.consumable && item.healLife > 0)
				{
					totalHealingItemCount += item.stack;
					if (item.healLife > bestHealingAmount)
					{
						bestHealingAmount = item.healLife;
						bestHealingItem = summary;
					}
				}

				if (item.consumable && item.healMana > 0)
				{
					totalManaItemCount += item.stack;
					if (item.healMana > bestManaAmount)
					{
						bestManaAmount = item.healMana;
						bestManaItem = summary;
					}
				}

				if (BossSummonItemTypes.Contains(item.type))
				{
					if (bossSummons.TryGetValue(item.type, out ItemSummary? existing))
					{
						bossSummons[item.type] = existing with { Stack = existing.Stack + item.stack };
					}
					else
					{
						bossSummons[item.type] = summary;
					}
				}
			}

			List<ItemSummary> bossSummonList = new List<ItemSummary>(bossSummons.Values);
			bossSummonList.Sort((a, b) => string.CompareOrdinal(a.Name, b.Name));

			return new InventorySnapshot(
				hotbar,
				armor,
				accessories,
				new HealingSummary(totalHealingItemCount, bestHealingItem, bestHealingAmount),
				new ManaSummary(totalManaItemCount, bestManaItem, bestManaAmount),
				bossSummonList.ToArray(),
				freeSlots);
		}

		internal static ItemSummary CreateItemSummary(Item item)
		{
			if (item.IsAir)
			{
				return ItemSummary.Empty;
			}

			return new ItemSummary(
				item.type,
				item.HoverName,
				item.stack);
		}

		private static HotbarSlotSummary[] CaptureHotbar(Player player)
		{
			List<HotbarSlotSummary> slots = new List<HotbarSlotSummary>();
			for (int slot = 0; slot < Math.Min(HotbarSlots, player.inventory.Length); slot++)
			{
				if (!player.inventory[slot].IsAir)
				{
					slots.Add(new HotbarSlotSummary(slot, CreateItemSummary(player.inventory[slot])));
				}
			}
			return slots.ToArray();
		}

		private static ArmorSnapshot CaptureArmor(Player player)
		{
			return new ArmorSnapshot(
				Head: CreateOptionalItemSummary(player.armor[0]),
				Body: CreateOptionalItemSummary(player.armor[1]),
				Legs: CreateOptionalItemSummary(player.armor[2]));
		}

		private static ItemSummary[] CaptureAccessories(Player player)
		{
			List<ItemSummary> accessories = new List<ItemSummary>();
			int firstAccessorySlot = Player.SupportedSlotsArmor;
			int accessorySlotCount = Player.SupportedSlotsAccs;

			for (int slot = firstAccessorySlot; slot < firstAccessorySlot + accessorySlotCount; slot++)
			{
				if (player.IsItemSlotUnlockedAndUsable(slot) && !player.armor[slot].IsAir)
				{
					accessories.Add(CreateItemSummary(player.armor[slot]));
				}
			}

			AccessorySlotLoader slotLoader = LoaderManager.Get<AccessorySlotLoader>();
			int moddedSlotCount = player.GetModPlayer<ModAccessorySlotPlayer>().LoadedSlotCount;
			for (int slot = 0; slot < moddedSlotCount; slot++)
			{
				Item item = slotLoader.Get(slot, player).FunctionalItem;
				if (slotLoader.ModdedIsSpecificItemSlotUnlockedAndUsable(slot, player, vanity: false)
					&& !item.IsAir)
				{
					accessories.Add(CreateItemSummary(item));
				}
			}

			return accessories.ToArray();
		}

		private static ItemSummary? CreateOptionalItemSummary(Item item)
		{
			return item.IsAir ? null : CreateItemSummary(item);
		}
	}
}
