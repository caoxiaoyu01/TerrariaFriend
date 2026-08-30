using System;
using TerrariaFriend.Triggering;

DateTimeOffset now = DateTimeOffset.UtcNow;
TimeSpan ttl = TimeSpan.FromSeconds(60);

Check(!TriggerQueuePolicy.IsExpired(
	Trigger(TriggerType.USER_QUERY, now.AddMinutes(-5)), now, ttl),
	"USER_QUERY 不应过期");
Check(TriggerQueuePolicy.ShouldDropPeriodic(true), "繁忙时应丢弃 PERIODIC");
Check(!TriggerQueuePolicy.IsExpired(
	Trigger(TriggerType.GAME_EVENT, now.AddSeconds(-30), GameEventType.SceneFeatureEntered), now, ttl),
	"60 秒内的普通 GAME_EVENT 应保留");
Check(TriggerQueuePolicy.IsExpired(
	Trigger(TriggerType.GAME_EVENT, now.AddSeconds(-61), GameEventType.SceneFeatureEntered), now, ttl),
	"超过 60 秒的普通 GAME_EVENT 应丢弃");
Check(!TriggerQueuePolicy.IsExpired(
	Trigger(TriggerType.GAME_EVENT, now.AddMinutes(-5), GameEventType.BossDefeated), now, ttl),
	"受保护 GAME_EVENT 不应过期");
Check(TriggerQueuePolicy.ShouldReplace(
	GameEventType.EquipmentChanged, GameEventType.EquipmentChanged),
	"EquipmentChanged 应保留最新状态");
Check(!TriggerQueuePolicy.ShouldReplace(
	GameEventType.BossDefeated, GameEventType.BossDefeated),
	"BossDefeated 不应被合并");
Check(!TriggerQueuePolicy.ShouldReplace(
	GameEventType.PlayerDied, GameEventType.PlayerDied),
	"PlayerDied 不应被合并");
Check(!TriggerQueuePolicy.ShouldReplace(
	GameEventType.ProgressMilestoneChanged, GameEventType.ProgressMilestoneChanged),
	"ProgressMilestoneChanged 不应被合并");

Console.WriteLine("TriggerQueuePolicy: 9 checks passed");

static TriggerEvent Trigger(
	TriggerType triggerType,
	DateTimeOffset timestamp,
	GameEventType? eventType = null)
{
	return new TriggerEvent(
		triggerType,
		timestamp,
		eventType == null ? null : new GameEvent(eventType.Value));
}

static void Check(bool condition, string message)
{
	if (!condition) throw new InvalidOperationException(message);
}

namespace TerrariaFriend.Triggering
{
	public enum TriggerType
	{
		USER_QUERY,
		GAME_EVENT,
		PERIODIC
	}

	public enum GameEventType
	{
		PlayerDied,
		BossDefeated,
		SceneFeatureEntered,
		ProgressMilestoneChanged,
		EquipmentChanged,
		WorldSessionEnded
	}

	public sealed record GameEvent(GameEventType EventType);

	public sealed record TriggerEvent(
		TriggerType TriggerType,
		DateTimeOffset Timestamp,
		GameEvent? GameEvent = null);
}
