#nullable enable

using System;
using System.Threading.Tasks;
using Terraria;
using Terraria.ModLoader;
using TerrariaFriend.Triggering;

namespace TerrariaFriend.AgentCommunication
{
	[Autoload(Side = ModSide.Client)]
	public sealed class AgentRuntimeSystem : ModSystem
	{
		private readonly AgentClient _client = new AgentClient();
		private Task<AgentResponse>? _activeRequest;

		public override void PostUpdatePlayers()
		{
			CompleteActiveRequest();

			if (Main.gameMenu || _activeRequest != null) return;
			if (!TriggerSystem.TryDequeue(out TriggerEvent? trigger) || trigger == null) return;

			// 不等待网络结果；每次只允许一个在途请求。
			_activeRequest = _client.SendTriggerAsync(trigger);
		}

		private void CompleteActiveRequest()
		{
			if (_activeRequest == null || !_activeRequest.IsCompleted) return;

			try
			{
				AgentResponse response = _activeRequest.GetAwaiter().GetResult();
				if (response.Success)
				{
					Mod.Logger.Info($"Agent response [{response.Action}]: {response.Message}");
				}
				else
				{
					Mod.Logger.Warn($"Agent request failed: {response.Error}");
				}
			}
			catch (Exception exception)
			{
				Mod.Logger.Error("Unexpected Agent request failure.", exception);
			}
			finally
			{
				_activeRequest = null;
			}
		}
	}
}
