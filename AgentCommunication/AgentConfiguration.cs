using System;

namespace TerrariaFriend.AgentCommunication
{
	// 智能体地址与网络参数
	public static class AgentConfiguration
	{
		public static readonly Uri TriggerEndpoint = new Uri("http://127.0.0.1:8000/agent/trigger");
		public static readonly Uri WorldSessionEndedEndpoint = new Uri("http://127.0.0.1:8000/agent/world-session-ended");

		// 推理循环最多包含四轮模型调用
		public static readonly TimeSpan RequestTimeout = TimeSpan.FromSeconds(120);
		public static readonly TimeSpan BoundarySignalTimeout = TimeSpan.FromSeconds(5);
	}
}
