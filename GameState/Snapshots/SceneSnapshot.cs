using System.Collections.Generic;

namespace TerrariaFriend.GameState.Snapshots
{
	// 玩家当前所在的局部环境
	public sealed record SceneSnapshot(
		IReadOnlyList<string> Biomes,
		string Layer,
		IReadOnlyList<string> SpecialScenes,
		IReadOnlyList<string> NearbyBuffs);
}
