#nullable enable

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using Terraria;
using Terraria.GameContent.Events;
using Terraria.ID;
using TerrariaFriend.GameState.Snapshots;

namespace TerrariaFriend.GameState.Collectors
{
	public static class WorldCollector
	{

		// 非入侵事件
		private static readonly (Func<bool> IsActive, string Id, string Name, WorldEventCategory Category)[] SimpleEvents =
		{
			(() => Main.bloodMoon, "BloodMoon", "Blood Moon", WorldEventCategory.Combat),
			(() => Main.eclipse, "SolarEclipse", "Solar Eclipse", WorldEventCategory.Combat),
			(() => Main.slimeRain, "SlimeRain", "Slime Rain", WorldEventCategory.Combat),
			(() => Main.pumpkinMoon, "PumpkinMoon", "Pumpkin Moon", WorldEventCategory.Combat),
			(() => Main.snowMoon, "FrostMoon", "Frost Moon", WorldEventCategory.Combat),
			(() => BirthdayParty.PartyIsUp, "Party", "Party", WorldEventCategory.Peaceful),
			(() => LanternNight.LanternsUp, "LanternNight", "Lantern Night", WorldEventCategory.Peaceful)
		};

		// 月相数字，影响npc售卖的物件种类
		private static readonly string[] MoonPhaseNames =
		{
			"Full Moon",
			"Waning Gibbous",
			"Third Quarter",
			"Waning Crescent",
			"New Moon",
			"Waxing Crescent",
			"First Quarter",
			"Waxing Gibbous"
		};

		// 将 Terraria 原始字段转换为不依赖游戏类型的世界快照
		public static WorldSnapshot Capture()
		{
			return new WorldSnapshot(
				CaptureTime(),
				CaptureWeather(),
				CaptureEvents());
		}

		private static TimeSnapshot CaptureTime()
		{
			float time = Utils.GetDayTimeAs24FloatStartingFromMidnight();
			int hour = (int)time;
			int minute = (int)((time - hour) * 60f);

			return new TimeSnapshot(
				Main.dayTime,
				$"{hour:00}:{minute:00}",
				GetMoonPhaseName(Main.moonPhase));
		}

		private static WeatherSnapshot CaptureWeather()
		{
			return new WeatherSnapshot(
				IsRaining: Main.raining,
				RainIntensity: Main.raining ? Main.maxRaining : 0f,
				WindSpeed: Main.windSpeedCurrent,
				IsSandstorm: Sandstorm.Happening);
		}

		// 每个状态独立判断，保留同一时刻并存的事件
		private static IReadOnlyList<WorldEventSnapshot> CaptureEvents()
		{
			List<WorldEventSnapshot> events = new List<WorldEventSnapshot>();

			foreach ((Func<bool> isActive, string id, string name, WorldEventCategory category) in SimpleEvents)
			{
				if (isActive())
				{
					events.Add(new WorldEventSnapshot(id, name, category));
				}
			}

			// 可以叠加入侵事件
			if (TryCaptureInvasion(out WorldEventSnapshot? invasion))
			{
				events.Add(invasion);
			}

			return events.ToArray();
		}

		private static bool TryCaptureInvasion(
			[NotNullWhen(true)] out WorldEventSnapshot? snapshot)
		{
			(string Id, string Name)? invasion = Main.invasionType switch
			{
				InvasionID.GoblinArmy => ("GoblinArmy", "Goblin Army"),
				InvasionID.PirateInvasion => ("PirateInvasion", "Pirate Invasion"),
				InvasionID.MartianMadness => ("MartianMadness", "Martian Madness"),
				InvasionID.SnowLegion => ("FrostLegion", "Frost Legion"),
				_ => null
			};

			if (!invasion.HasValue)
			{
				snapshot = null;
				return false;
			}

			// 入侵剩余数量换算成 0~1 的已完成比例
			float? progress = Main.invasionSizeStart > 0
				? Math.Clamp(1f - (float)Main.invasionSize / Main.invasionSizeStart, 0f, 1f)
				: null;

			snapshot = new WorldEventSnapshot(
				invasion.Value.Id,
				invasion.Value.Name,
				WorldEventCategory.Invasion,
				progress);
			return true;
		}

		private static string GetMoonPhaseName(int moonPhase)
		{
			return moonPhase >= 0 && moonPhase < MoonPhaseNames.Length
				? MoonPhaseNames[moonPhase]
				: "Unknown";
		}
	}
}
