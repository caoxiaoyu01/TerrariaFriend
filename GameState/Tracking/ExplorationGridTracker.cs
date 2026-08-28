#nullable enable

using System.Collections.Generic;
using System.Linq;
using Terraria.ModLoader;
using TerrariaFriend.GameState.Persistence;
using TerrariaFriend.GameState.Snapshots;
using TerrariaFriend.Triggering;

namespace TerrariaFriend.GameState.Tracking
{
	// 按固定大小划分地图 用来判断玩家是否到达新区域
	public sealed class ExplorationGridTracker
	{
		public const int ExplorationCellSize = 100;

		private ExplorationCell? _lastCell;
		private SceneEnvironment? _lastEnvironment;
		private readonly HashSet<ExplorationCell> _sessionVisitedCells = new HashSet<ExplorationCell>();

		public bool TryDiscover(
			GameSnapshot snapshot,
			out GameEvent? gameEvent,
			out GameEventContext? eventContext)
		{
			ExplorationCell currentCell = FromPosition(snapshot.Player);
			SceneEnvironment currentEnvironment = CaptureEnvironment(snapshot.Scene);

			// 第一次采集只记住起点 不触发探索事件
			if (_lastCell == null)
			{
				MarkCellVisited(currentCell);
				_lastCell = currentCell;
				_lastEnvironment = currentEnvironment;
				gameEvent = null;
				eventContext = null;
				return false;
			}

			if (_lastCell.Value == currentCell)
			{
				_lastEnvironment = currentEnvironment;
				gameEvent = null;
				eventContext = null;
				return false;
			}

			SceneEnvironment previousEnvironment = _lastEnvironment!;
			_lastCell = currentCell;
			_lastEnvironment = currentEnvironment;

			if (!MarkCellVisited(currentCell))
			{
				gameEvent = null;
				eventContext = null;
				return false;
			}

			gameEvent = new GameEvent(
				GameEventType.NewAreaDiscovered,
				CellX: currentCell.X,
				CellY: currentCell.Y);
			eventContext = new GameEventContext(
				ProgressionStage: snapshot.Progress.CurrentStage.Id,
				Biomes: currentEnvironment.Biomes,
				Layer: currentEnvironment.Layer,
				MiniBiomes: currentEnvironment.MiniBiomes,
				SpecialAreas: currentEnvironment.SpecialAreas,
				PreviousBiomes: previousEnvironment.Biomes,
				PreviousLayer: previousEnvironment.Layer,
				PreviousMiniBiomes: previousEnvironment.MiniBiomes,
				PreviousSpecialAreas: previousEnvironment.SpecialAreas);
			return true;
		}

		public void Reset()
		{
			_lastCell = null;
			_lastEnvironment = null;
			_sessionVisitedCells.Clear();
		}

		public static ExplorationCell FromPosition(PlayerSnapshot player)
		{
			return new ExplorationCell(
				(int)(player.PositionTileX / ExplorationCellSize),
				(int)(player.PositionTileY / ExplorationCellSize));
		}

		private static SceneEnvironment CaptureEnvironment(SceneSnapshot scene)
		{
			return new SceneEnvironment(
				scene.Biomes.ToArray(),
				scene.Layer,
				scene.MiniBiomes.ToArray(),
				scene.SpecialAreas.ToArray());
		}

		private bool MarkCellVisited(ExplorationCell cell)
		{
			// 本次游戏内再记一份 防止多人同步后重复触发
			if (!_sessionVisitedCells.Add(cell)) return false;
			return ModContent.GetInstance<CompanionWorldState>().MarkCellVisited(cell);
		}

		private sealed record SceneEnvironment(
			IReadOnlyList<string> Biomes,
			string Layer,
			IReadOnlyList<string> MiniBiomes,
			IReadOnlyList<string> SpecialAreas);
	}
}
