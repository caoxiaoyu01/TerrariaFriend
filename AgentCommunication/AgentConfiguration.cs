using System;

namespace TerrariaFriend.AgentCommunication
{
	// Agent 地址与网络参数
	public static class AgentConfiguration
	{
		public static readonly Uri TriggerEndpoint = new Uri("http://127.0.0.1:8000/agent/trigger");

		// Reasoning Loop 最多包含四轮模型调用
		public static readonly TimeSpan RequestTimeout = TimeSpan.FromSeconds(120);
	}
}
